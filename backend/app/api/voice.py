"""
@file backend/app/api/voice.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import base64

import edge_tts
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

# For a local, free, professional setup:
# - STT: faster-whisper (local, high performance, completely free)
# - TTS: We keep edge-tts as a fast free cloud alternative, but structure the code 
#        so it can be easily swapped with Kokoro TTS or Coqui XTTSv2 for local studio-quality voice.

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Initialize STT model lazily to save RAM if voice is not used
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        print("[Voice] Loading faster-whisper model (local, free, professional)...")
        # 'small' or 'base' are great for real-time. 'large-v3' is studio quality but needs more VRAM.
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model

async def professional_tts_stream(text: str):
    """
    Synthesizes speech.
    Currently uses edge-tts (free). 
    To upgrade to ultra-professional local TTS without paying, you can swap this with Kokoro TTS or Coqui XTTS.
    """
    communicate = edge_tts.Communicate(text, "it-IT-ElsaNeural")
    tts_audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            tts_audio_data += chunk["data"]
            # In a true streaming setup, we would yield chunks here.
    return base64.b64encode(tts_audio_data).decode("utf-8")

@router.websocket("/stream")
async def voice_stream_endpoint(websocket: WebSocket):
    """
    Advanced Bi-directional Voice Streaming Endpoint (M7).
    """
    from app.core.security import IdentityService
    from app.core.db import SessionLocal
    from app.runtime.aurora import run_aurora_agent
    
    # Authenticate WebSocket (Using subprotocols or query param, for simplicity assume query token)
    token = websocket.query_params.get("token")
    principal = None
    if token:
        with SessionLocal() as db:
            session = IdentityService.validate_session(db, token)
            if session:
                from app.core.security import Principal, RoleEnum
                principal = Principal(id=session.user_id, role=RoleEnum.USER, workspace_id="default")
                
    await websocket.accept()
    if not principal:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    print("[Voice] Client authenticated and connected to real-time voice stream.")
    
    model = get_whisper_model()
    
    try:
        audio_buffer = bytearray()
        
        while True:
            # We expect the client to send raw PCM audio or a structured JSON indicating end of speech
            data = await websocket.receive()
            
            if "bytes" in data:
                audio_buffer.extend(data["bytes"])
                
            elif "text" in data:
                # Client signals it has finished speaking and wants processing
                msg = data["text"]
                if msg == "END_SPEECH":
                    if len(audio_buffer) == 0:
                        continue
                        
                    await websocket.send_json({"type": "status", "message": "Transcribing..."})
                    
                    # Convert bytearray to audio file/stream for whisper
                    import io
                    # Assuming client sends raw 16kHz PCM or Wav. Faster whisper can accept a file-like object
                    # For robust implementation, we save it temporarily to disk or use soundfile to decode
                    import tempfile
                    import os
                    
                    # Dump to temp file to be sure (client must send proper wav headers for simplicity, or we decode raw PCM)
                    # Assuming client sends webm or wav chunks:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(audio_buffer)
                        tmp_path = tmp.name
                        
                    segments, info = model.transcribe(tmp_path, beam_size=5, language="it")
                    transcript = "".join([segment.text for segment in segments]).strip()
                    os.remove(tmp_path)
                    audio_buffer.clear()
                    
                    if not transcript:
                        continue
                        
                    await websocket.send_json({"type": "transcript", "text": transcript})
                    await websocket.send_json({"type": "status", "message": "Thinking..."})
                    
                    # Route to A.U.R.O.R.A
                    import uuid
                    session_id = f"voice-{principal.id}"
                    
                    # Invoke Agent
                    final_state = await run_aurora_agent(session_id, transcript, principal)
                    reply_text = final_state["messages"][-1].content
                    
                    await websocket.send_json({"type": "reply", "text": reply_text})
                    await websocket.send_json({"type": "status", "message": "Speaking..."})
                    
                    # TTS
                    tts_b64 = await professional_tts_stream(reply_text)
                    await websocket.send_json({"type": "audio", "data": tts_b64})
                    await websocket.send_json({"type": "status", "message": "Listening..."})
                    
    except WebSocketDisconnect:
        print("[Voice] Client disconnected from voice stream.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Voice] Stream error: {e}")
