"""
@file backend/main.py
@description Main FastAPI application entrypoint for ÆHub.

This module defines the HTTP/WebSocket application boundary, authentication
middleware, security headers, event streaming, media helpers, startup lifecycle,
and the authenticated WebSocket orchestration channel.

Security invariants:
- API requests require a valid persistent session.
- WebSocket connections authenticate from the session cookie only.
- Authenticated clients cannot override the server-bound session identity.
- Tenant/workspace identity is derived exclusively from the authenticated
  persistent session.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime

import edge_tts
import httpx
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.agents import orchestrator
from app.api import academic, media, voice
from app.core import database
from app.core.event_bus import event_bus
from app.core.telemetry import (
    setup_telemetry,
    shutdown_telemetry,
)
from app.workers.scheduler import proactive_scheduler
from app.workflows.autonomous import register_workflows


# ==============================================================================
# APPLICATION INITIALIZATION
# ==============================================================================

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown resources.
    """
    from sqlalchemy import text

    from app.core.db import engine
    from app.core.telemetry import instrument_sqlalchemy
    from app.domain.models import Base

    instrument_sqlalchemy(
        engine
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE EXTENSION IF NOT EXISTS vector"
            )
        )

    Base.metadata.create_all(
        bind=engine
    )

    database.init_db()
    register_workflows()
    proactive_scheduler.start()

    print(
        "[OK] Centralized PostgreSQL database schema initialized."
    )

    try:
        yield
    finally:
        proactive_scheduler.stop()
        shutdown_telemetry()


app = FastAPI(
    title="AeSouls Hub API Server",
    lifespan=lifespan,
)

setup_telemetry(app)


# ==============================================================================
# SECURITY CONFIGURATION
# ==============================================================================

AEHUB_SECRET_KEY = settings.AEHUB_SECRET_KEY

if (
    not AEHUB_SECRET_KEY
    or AEHUB_SECRET_KEY == "default-unsafe-key"
):
    print(
        "[CRITICAL] AEHUB_SECRET_KEY is not configured securely. "
        "Application startup aborted."
    )
    sys.exit(1)


# ==============================================================================
# HEALTH CHECK
# ==============================================================================


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Return the application health status used by orchestration probes.
    """
    return {
        "status": "ok",
    }


# ==============================================================================
# GLOBAL HTTP AUTHENTICATION
# ==============================================================================


@app.middleware("http")
async def verify_api_key(
    request: Request,
    call_next,
):
    """
    Validate the persistent authenticated session for protected API traffic.

    Authentication is intentionally performed against the server-side session
    store. The resulting session object is never reconstructed from arbitrary
    client-supplied identifiers.
    """
    if request.method == "OPTIONS":
        return await call_next(request)

    protected_api_path = (
        request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/auth/")
    )

    if protected_api_path:
        from app.core.cache import CacheService
        from app.core.db import SessionLocal
        from app.core.security import IdentityService

        auth_header = request.headers.get(
            "Authorization"
        )

        cookie_token = request.cookies.get(
            "aehub_session_token"
        )

        session_token = cookie_token

        if (
            auth_header
            and auth_header.startswith("Bearer ")
        ):
            session_token = auth_header.split(
                " ",
                1,
            )[1]

        with SessionLocal() as db:
            session = (
                IdentityService.validate_session(
                    db,
                    session_token,
                )
                if session_token
                else None
            )

            if not session:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": (
                            "Unauthorized access. "
                            "Invalid or missing session."
                        )
                    },
                )

            path = request.url.path

            limit = 60
            window = 60
            limit_key = "api"

            if (
                path.startswith(
                    "/api/orchestrator/listen"
                )
                or "upload" in path
            ):
                limit = 10
                window = 60
                limit_key = "upload"

            elif path.startswith(
                "/api/orchestrator/ask"
            ):
                limit = 20
                window = 60
                limit_key = "llm"

            is_allowed = (
                await CacheService.check_rate_limit(
                    identifier=(
                        f"{limit_key}:{session.user_id}"
                    ),
                    limit=limit,
                    window_seconds=window,
                )
            )

            if not is_allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "Too Many Requests. "
                            "Rate limit exceeded."
                        )
                    },
                )

    return await call_next(request)


# ==============================================================================
# MIDDLEWARE STACK
# ==============================================================================

from app.core.security_middleware import AdvancedSecurityMiddleware


app.add_middleware(
    AdvancedSecurityMiddleware
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv(
            "FRONTEND_URL",
            "http://localhost:3000",
        )
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# ROUTER REGISTRATION
# ==============================================================================

from app.api import auth


app.include_router(auth.router)
app.include_router(media.router)
app.include_router(academic.router)
app.include_router(voice.router)
app.include_router(orchestrator.router)


# ==============================================================================
# SECURITY HEADERS
# ==============================================================================


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    """
    Add browser-facing security headers to every HTTP response.
    """
    response = await call_next(request)

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Strict-Transport-Security"
    ] = (
        "max-age=31536000; includeSubDomains"
    )

    return response


# ==============================================================================
# SERVER-SENT EVENTS
# ==============================================================================


async def sse_event_generator(
    session_id: str,
    request: Request,
):
    """
    Stream EventBus messages for one authenticated session.
    """
    queue = event_bus.subscribe(session_id)

    try:
        while True:
            if await request.is_disconnected():
                break

            message = await queue.get()

            yield f"data: {message}\n\n"

    finally:
        event_bus.unsubscribe(
            session_id,
            queue,
        )


@app.get("/api/events")
async def get_events_stream(
    request: Request,
):
    """
    Stream real-time application events for the authenticated principal.
    """
    from app.core.security import resolve_principal

    try:
        principal = resolve_principal(request)
    except Exception:
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Unauthorized",
            },
        )

    session_id = principal.id

    return StreamingResponse(
        sse_event_generator(
            session_id,
            request,
        ),
        media_type="text/event-stream",
    )


# ==============================================================================
# AUDIO INPUT PROCESSING
# ==============================================================================


async def process_audio_to_text(
    base64_audio: str,
) -> str:
    """
    Decode inbound Base64 audio and submit it to the Groq Whisper endpoint.

    Temporary audio files are deleted in the finally block regardless of the
    transcription result.
    """
    temp_path = None

    try:
        if "," in base64_audio:
            base64_audio = base64_audio.split(
                ",",
                1,
            )[1]

        audio_bytes = base64.b64decode(
            base64_audio
        )

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".webm",
        ) as temp:
            temp.write(audio_bytes)
            temp_path = temp.name

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:
            with open(
                temp_path,
                "rb",
            ) as file_handle:
                response = await client.post(
                    (
                        "https://api.groq.com/"
                        "openai/v1/audio/transcriptions"
                    ),
                    files={
                        "file": (
                            os.path.basename(
                                temp_path
                            ),
                            file_handle,
                            "audio/webm",
                        )
                    },
                    data={
                        "model": "whisper-large-v3",
                    },
                    headers={
                        "Authorization": (
                            "Bearer "
                            f"{os.getenv('GROQ_API_KEY')}"
                        )
                    },
                )

        if response.status_code == 200:
            return response.json().get(
                "text",
                "",
            )

        return "Transcription error."

    except Exception as exc:
        print(
            f"STT Error: {exc}"
        )
        return "Audio processing failed."

    finally:
        if (
            temp_path
            and os.path.exists(temp_path)
        ):
            os.remove(temp_path)


# ==============================================================================
# AUDIO OUTPUT PROCESSING
# ==============================================================================


async def process_text_to_audio(
    text: str,
) -> str:
    """
    Generate neural speech audio, encode it as Base64, and remove the
    temporary filesystem artifact immediately after reading it.
    """
    try:
        os.makedirs(
            "workspace/audio_cache",
            exist_ok=True,
        )

        file_path = os.path.join(
            "workspace/audio_cache",
            (
                "response_"
                f"{int(datetime.now().timestamp())}.mp3"
            ),
        )

        communicate = edge_tts.Communicate(
            text,
            "it-IT-ElsaNeural",
        )

        await communicate.save(
            file_path
        )

        with open(
            file_path,
            "rb",
        ) as file_handle:
            base64_data = base64.b64encode(
                file_handle.read()
            ).decode("utf-8")

        if os.path.exists(
            file_path
        ):
            os.remove(file_path)

        return base64_data

    except Exception as exc:
        print(
            f"TTS Error: {exc}"
        )
        return ""


# ==============================================================================
# AUTHENTICATED WEBSOCKET ORCHESTRATOR
# ==============================================================================


@app.websocket("/ws/orchestrator")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """
    Manage the authenticated real-time orchestration channel.

    The WebSocket session identity is derived once from the validated
    persistent session. Client payloads are never allowed to override the
    authenticated session or workspace context.
    """
    from app.core.db import SessionLocal
    from app.core.security import (
        IdentityService,
        Principal,
    )

    client_token = websocket.cookies.get(
        "aehub_session_token"
    )

    with SessionLocal() as db:
        session = (
            IdentityService.validate_session(
                db,
                client_token,
            )
            if client_token
            else None
        )

    if not session:
        print(
            "[ERROR] Unauthorized WebSocket connection blocked."
        )

        await websocket.close(
            code=1008
        )
        return

    if not session.workspace_id:
        print(
            "[ERROR] WebSocket session has no workspace binding."
        )

        await websocket.close(
            code=1008
        )
        return

    ws_principal = Principal(
        id=session.user_id,
        role=session.role,
        workspace_id=session.workspace_id,
    )

    # The downstream orchestration session is server-derived and immutable.
    authenticated_session_id = session.user_id

    await websocket.accept()

    print(
        "[OK] Authenticated WebSocket connection established."
    )

    async def safe_send(
        payload: dict,
    ):
        """
        Send a JSON payload while converting transport failures to a
        WebSocketDisconnect exception.
        """
        try:
            await websocket.send_json(
                payload
            )
        except Exception as exc:
            raise WebSocketDisconnect() from exc

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            if not isinstance(
                payload,
                dict,
            ):
                await safe_send(
                    {
                        "type": "error",
                        "data": "Invalid WebSocket payload.",
                    }
                )
                continue

            input_type = payload.get(
                "type",
                "text_input",
            )

            user_context = payload.get(
                "context",
                {},
            )

            # SECURITY BOUNDARY:
            # Never accept session_id from the browser payload.
            session_id = authenticated_session_id

            if input_type == "audio_input":
                user_text = await process_audio_to_text(
                    payload.get(
                        "data",
                        "",
                    )
                )
            else:
                user_text = payload.get(
                    "data",
                    "",
                )

            if not user_text:
                continue

            await safe_send(
                {
                    "type": "status",
                    "data": "thinking",
                }
            )

            from app.agents.orchestrator import (
                AESOUL_SYSTEM_PROMPT,
                generate_ai_response,
            )

            response_payload = (
                await generate_ai_response(
                    user_text,
                    AESOUL_SYSTEM_PROMPT,
                    str(user_context),
                    session_id,
                    principal=ws_principal,
                )
            )

            if not response_payload:
                continue

            await safe_send(
                {
                    "type": "stream_end",
                    "full_text": response_payload[
                        "transcription"
                    ],
                }
            )

            if response_payload.get(
                "audio_base64"
            ):
                await safe_send(
                    {
                        "type": "audio_stream",
                        "data": response_payload[
                            "audio_base64"
                        ],
                    }
                )

    except WebSocketDisconnect:
        print(
            "[INFO] WebSocket client disconnected."
        )

    except Exception as exc:
        print(
            "[ERROR] WebSocket orchestration failure: "
            f"{exc}"
        )


# ==============================================================================
# LOCAL DEVELOPMENT ENTRYPOINT
# ==============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3002,
        reload=True,
    )
