"""
@file backend/main.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import asyncio
import base64
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime

import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.agents import orchestrator
from app.api import academic, media, voice

# Import the centralized relational persistence controller
from app.core import database
from app.core.event_bus import event_bus
from app.workers.scheduler import proactive_scheduler

load_dotenv()

# Windows platform optimization runtime fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.core.config import settings
from app.core.telemetry import setup_telemetry

app = FastAPI(title="AeSouls Hub API Server")

# Phase 4: Observability Plane
setup_telemetry(app)

# SECURITY ANCHOR: Fetch the master authorization token from environment variables.
AEHUB_SECRET_KEY = settings.AEHUB_SECRET_KEY
if not AEHUB_SECRET_KEY or AEHUB_SECRET_KEY == "default-unsafe-key":
    print("[CRITICAL] AEHUB_SECRET_KEY not set securely. Halting for security.")
    sys.exit(1)


# =====================================================================
# GLOBAL AUTHENTICATION MIDDLEWARE (THE "LUCCHETTO")
# =====================================================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """
    Global security checkpoint. Intercepts all incoming HTTP traffic.
    Requires a valid session token.
    """
    # Always allow CORS preflight requests to pass through
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
        from app.core.security import IdentityService
        from app.core.db import SessionLocal
        from app.core.cache import CacheService
        auth_header = request.headers.get("Authorization")
        cookie_token = request.cookies.get("aehub_session_token")
        
        session_token = cookie_token
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
            
        with SessionLocal() as db:
            session = IdentityService.validate_session(db, session_token) if session_token else None
            if not session:
                return JSONResponse(
                    status_code=401, 
                    content={"detail": "Unauthorized access. Invalid or missing session."}
                )
                
            # M4: Rate Limiting
            is_allowed = await CacheService.check_rate_limit(
                identifier=f"user:{session.user_id}",
                limit=60, # 60 requests
                window_seconds=60 # per minute
            )
            if not is_allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests. Rate limit exceeded."}
                )

    # Proceed to the requested endpoint if authentication is successful
    response = await call_next(request)
    return response


# =====================================================================
# CORS CONFIGURATION (MOBILE SAFE BOUNDARY)
# =====================================================================
from app.core.security_middleware import AdvancedSecurityMiddleware

app.add_middleware(AdvancedSecurityMiddleware)
app.add_middleware(SecurityAuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import auth
app.include_router(auth.router)

# =====================================================================
# SECURITY HEADERS MIDDLEWARE
# =====================================================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Register application routers under decoupled sub-context boundaries
app.include_router(media.router)
app.include_router(academic.router)
app.include_router(voice.router)
app.include_router(orchestrator.router)


# =====================================================================
# SERVER-SENT EVENTS (SSE) EVENT BUS STREAM
# =====================================================================
async def sse_event_generator(session_id: str, request: Request):
    """
    Generator that pulls messages from the EventBus and yields them
    in standard Server-Sent Events (SSE) format.
    """
    queue = event_bus.subscribe(session_id)
    try:
        while True:
            # Check if the client has disconnected
            if await request.is_disconnected():
                break
            
            message = await queue.get()
            yield f"data: {message}\n\n"
    finally:
        event_bus.unsubscribe(session_id, queue)


@app.get("/api/events")
async def get_events_stream(request: Request):
    """
    SSE endpoint for streaming real-time logs and agent states to the frontend.
    """
    from app.core.security import resolve_principal
    try:
        principal = resolve_principal(request)
        session_id = principal.id
    except:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    
    return StreamingResponse(sse_event_generator(session_id, request), media_type="text/event-stream")


from app.workflows.autonomous import register_workflows


# Initialize database storage schemas during the application startup lifecycle
@app.on_event("startup")
def startup_db():
    from app.core.db import engine
    from app.domain.models import Base
    from app.core.telemetry import instrument_sqlalchemy
    from sqlalchemy import text
    
    # Phase 6: Instrument Database Tracing
    instrument_sqlalchemy(engine)
    
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
    Base.metadata.create_all(bind=engine)
    
    database.init_db()
    register_workflows()
    proactive_scheduler.start()
    print("[OK] Centralized PostgreSQL Database Schema Initialized")


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
        os.makedirs("workspace/audio_cache", exist_ok=True)

        file_path = os.path.join("workspace/audio_cache", f"response_{int(datetime.now().timestamp())}.mp3")

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
    from app.core.security import IdentityService
    from app.core.db import SessionLocal
    # SECURITY ANCHOR: Validate session token passed via cookies ONLY (no query params)
    client_token = websocket.cookies.get("aehub_session_token")
    with SessionLocal() as db:
        session = IdentityService.validate_session(db, client_token) if client_token else None
    
    if not session:
        print("[ERROR] Unauthorized WebSocket connection attempt blocked.")
        await websocket.close(code=1008)  # 1008 corresponds to Policy Violation
        return

    await websocket.accept()
    print("[OK] Client connection established on WebSocket node")

    os.getenv("OPENROUTER_API_KEY")
    session_id = session.user_id

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

            # Canonical Execution Path
            from app.agents.orchestrator import AESOUL_SYSTEM_PROMPT, generate_ai_response
            
            response_payload = await generate_ai_response(
                user_text, AESOUL_SYSTEM_PROMPT, str(user_context), session_id
            )
            
            if response_payload:
                await safe_send({"type": "stream_end", "full_text": response_payload["transcription"]})
                if response_payload.get("audio_base64"):
                    await safe_send({"type": "audio_stream", "data": response_payload["audio_base64"]})

    except WebSocketDisconnect:
        print("🔴 Client connection terminated on WebSocket node")

    except Exception as e:
        print(f"❌ Critical exception encountered on WebSocket pipeline: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3002, reload=True)
