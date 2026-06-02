import asyncio
import base64
import json
import os
import sys
import tempfile
from datetime import datetime

import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from litellm import RateLimitError, acompletion

# Import the centralized relational persistence controller
import database
from routers import academic, media, orchestrator

load_dotenv()

# Windows platform optimization runtime fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="AeSouls Hub API Server")

# SECURITY ANCHOR: Fetch the master authorization token from environment variables.
AEHUB_SECRET_KEY = os.getenv("AEHUB_SECRET_KEY", "default-unsafe-key")


# =====================================================================
# GLOBAL AUTHENTICATION MIDDLEWARE (THE "LUCCHETTO")
# =====================================================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):

    # Enforce strict token validation for all API endpoints
    if request.url.path.startswith("/api/"):
        client_key = request.headers.get("X-AeHub-Key")
        
        # 👇 INSERISCI QUESTE RIGHE:
        print("\n--- DEBUG SICUREZZA ---")
        print(f"Chiave che il Backend ha letto dal file .env: '{AEHUB_SECRET_KEY}'")
        print(f"Chiave che il Frontend ha inviato: '{client_key}'")
        print("-----------------------\n")

        if not client_key or client_key != AEHUB_SECRET_KEY:
            return JSONResponse(
                status_code=401, 
                content={"detail": "Unauthorized access. Invalid or missing X-AeHub-Key."}
            )

    """
    Global security checkpoint. Intercepts all incoming HTTP traffic.
    Requires a valid 'X-AeHub-Key' header matching the environment secret
    to process any route under the '/api/' path. Bypasses preflight CORS checks.
    """
    # Always allow CORS preflight requests to pass through
    if request.method == "OPTIONS":
        return await call_next(request)

    # Enforce strict token validation for all API endpoints
    if request.url.path.startswith("/api/"):
        client_key = request.headers.get("X-AeHub-Key")
        if not client_key or client_key != AEHUB_SECRET_KEY:
            # Drop the request immediately if unauthorized, protecting compute resources
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized access. Invalid or missing X-AeHub-Key."},
            )

    # Proceed to the requested endpoint if authentication is successful
    response = await call_next(request)
    return response


# =====================================================================
# CORS CONFIGURATION (MOBILE SAFE BOUNDARY)
# =====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register application routers under decoupled sub-context boundaries
app.include_router(media.router)
app.include_router(academic.router)
app.include_router(orchestrator.router)


# Initialize database storage schemas during the application startup lifecycle
@app.on_event("startup")
def startup_db():
    database.init_db()
    print("🟢 Centralized SQLite Database Schema Initialized")


# =====================================================================
# AUDIO -> TEXT (SPEECH TO TEXT CONVERSION PROCESSING)
# =====================================================================
async def process_audio_to_text(base64_audio: str):
    """
    Decodes inbound Base64 audio wave packets, maps them into volatile storage,
    and forwards the binary block directly to Groq's hardware-accelerated Whisper model.
    """
    temp_path = None
    try:
        if "," in base64_audio:
            base64_audio = base64_audio.split(",")[1]

        audio_bytes = base64.b64decode(base64_audio)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp:
            temp.write(audio_bytes)
            temp_path = temp.name

        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(temp_path, "rb") as f:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    files={"file": (os.path.basename(temp_path), f, "audio/webm")},
                    data={"model": "whisper-large-v3"},
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                )

        if response.status_code == 200:
            return response.json().get("text", "")

        return "Transcription error."

    except Exception as e:
        print(f"STT Error: {e}")
        return "Audio processing failed."

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# =====================================================================
# TEXT -> AUDIO (NEURAL TEXT TO SPEECH CONVERSION PROCESSING)
# =====================================================================
async def process_text_to_audio(text: str):
    """
    Synthesizes clean textual intelligence into neural audio streams, encodes them
    to Base64, and purges system assets from disk to preserve a zero-byte leak footprint.
    """
    try:
        os.makedirs("audio_cache", exist_ok=True)

        file_path = os.path.join("audio_cache", f"response_{int(datetime.now().timestamp())}.mp3")

        communicate = edge_tts.Communicate(text, "it-IT-ElsaNeural")
        await communicate.save(file_path)

        with open(file_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")

        # RESOURCE PROTECTION: Instantly delete physical asset to mitigate disk leaks
        if os.path.exists(file_path):
            os.remove(file_path)

        return base64_data

    except Exception as e:
        print(f"TTS Error: {e}")
        return ""


# =====================================================================
# WEBSOCKET ORCHESTRATOR (REAL-TIME ISOLATED DUPLEX CHANNEL)
# =====================================================================
@app.websocket("/ws/orchestrator")
async def websocket_endpoint(websocket: WebSocket):
    """
    Manages continuous duplex WebSocket communication streams. Extracts state tokens
    to segment settings matrices, history recall buffers, and loops on a per-user layer.
    """
    # SECURITY ANCHOR: Validate token passed via query parameters (e.g. ?token=...)
    client_token = websocket.query_params.get("token")
    if client_token != AEHUB_SECRET_KEY:
        print("🔴 Unauthorized WebSocket connection attempt blocked.")
        await websocket.close(code=1008)  # 1008 corresponds to Policy Violation
        return

    await websocket.accept()
    print("🟢 Client connection established on WebSocket node")

    api_key = os.getenv("OPENROUTER_API_KEY")
    session_id = websocket.query_params.get("session_id", "default-session")

    async def safe_send(payload: dict):
        try:
            await websocket.send_json(payload)
        except Exception as e:
            # Re-raise with traceback context to satisfy Ruff exception safety rules
            raise WebSocketDisconnect() from e

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            input_type = payload.get("type", "text_input")
            user_context = payload.get("context", {})
            session_id = payload.get("session_id", session_id)

            user_text = (
                await process_audio_to_text(payload.get("data"))
                if input_type == "audio_input"
                else payload.get("data")
            )

            if not user_text:
                continue

            await safe_send({"type": "status", "data": "thinking"})

            session_config = database.get_settings(session_id)

            system_prompt = (
                "You are AeSoul, the dashboard AI. "
                f"Context: {json.dumps(user_context)}. "
                "Use only provided data. No markdown."
            )

            messages = [{"role": "system", "content": system_prompt}]

            if session_config["deep_mode"]:
                messages.append(
                    {
                        "role": "system",
                        "content": "OVERRIDE: You are in DEEP REASONING mode. Ignore brevity constraints. Provide detailed analysis.",
                    }
                )

            historical_context = database.get_recent_chat(session_id, limit=5)
            messages.extend(historical_context)
            messages.append({"role": "user", "content": user_text})

            retries = 3
            while retries > 0:
                try:
                    response = await acompletion(
                        model="openrouter/openai/gpt-oss-120b:free",
                        api_key=api_key,
                        messages=messages,
                        temperature=session_config["temperature"],
                        max_tokens=session_config["max_tokens"],
                        stream=True,
                    )

                    full_text = ""
                    async for chunk in response:
                        delta = chunk.choices[0].delta.content or ""
                        full_text += delta

                    await safe_send({"type": "stream_end", "full_text": full_text})

                    audio = await process_text_to_audio(full_text)
                    if audio:
                        await safe_send({"type": "audio_stream", "data": audio})

                    database.save_chat(session_id, user_text, full_text)
                    break

                except RateLimitError:
                    retries -= 1
                    await safe_send({"type": "status", "data": "rate_limited_retrying"})
                    await asyncio.sleep(3)

                except Exception as e:
                    print(f"LLM inference failure on WebSocket: {e}")
                    await safe_send({"type": "error", "message": "Generation failed"})
                    break

    except WebSocketDisconnect:
        print("🔴 Client connection terminated on WebSocket node")

    except Exception as e:
        print(f"❌ Critical exception encountered on WebSocket pipeline: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3002, reload=True)
