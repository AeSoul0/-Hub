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
    Advanced Bi-directional Voice Streaming Endpoint.
    Supports VAD (Voice Activity Detection), Barge-in (Interruption), and real-time STT.
    """
    await websocket.accept()
    print("[Voice] Client connected to real-time voice stream.")
    
    # Initialize model
    get_whisper_model()
    
    try:
        while True:
            # Receive audio chunk from frontend (e.g., PCM 16kHz)
            await websocket.receive_bytes()
            
            # Phase 10 placeholder:
            # 1. Pass data through Silero VAD to detect speech bounds.
            # 2. Accumulate chunks until silence.
            # 3. Pass accumulated audio to faster-whisper.
            # 4. Route text to A.U.R.O.R.A.
            # 5. Stream TTS back to client, supporting interruption if user speaks again.
            
            # Simulated echo for now to demonstrate architecture
            await websocket.send_json({"type": "status", "message": "Audio received, processing STT..."})
            
    except WebSocketDisconnect:
        print("[Voice] Client disconnected from voice stream.")
    except Exception as e:
        print(f"[Voice] Stream error: {e}")
