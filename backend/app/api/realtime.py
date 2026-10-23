"""
@file backend/app/api/realtime.py
@description Realtime transport boundary for SSE, WebSocket, and speech helpers.

This module isolates transport-specific concerns from the FastAPI application
composition root. It owns authenticated realtime endpoints and audio conversion
helpers while delegating conversational execution to the existing orchestration
service.

Architectural boundary:
- HTTP/SSE/WebSocket transport is handled here.
- Authentication context is resolved here for transport-specific channels.
- Agent execution remains delegated to app.agents.orchestrator.
- No orchestration state or business policy is owned by this module.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
from datetime import datetime
from typing import Literal

import edge_tts
import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.event_bus import event_bus


router = APIRouter(tags=["realtime"])


# ==============================================================================
# SERVER-SIDE AUDIO HELPERS
# ==============================================================================


async def process_audio_to_text(base64_audio: str) -> str:
    """
    Decode Base64 audio and submit it to the configured Groq transcription API.

    The helper owns only temporary-file handling and the external HTTP request.
    Agent execution and authentication remain outside this function.
    """
    if not (os.getenv("GROQ_API_KEY") or "").strip():
        return "Voice input is off: GROQ_API_KEY is not set."

    temp_path = None

    try:
        if "," in base64_audio:
            base64_audio = base64_audio.split(",", 1)[1]

        audio_bytes = base64.b64decode(base64_audio)

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".webm",
        ) as temp:
            temp.write(audio_bytes)
            temp_path = temp.name

        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(temp_path, "rb") as file_handle:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    files={
                        "file": (
                            os.path.basename(temp_path),
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
            return response.json().get("text", "")

        return "Transcription error."

    except Exception as exc:
        print(f"STT Error: {exc}")
        return "Audio processing failed."

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


async def process_text_to_audio(text: str) -> str:
    """
    Generate speech audio, encode it as Base64, and remove the temporary file.

    This helper is intentionally retained during the first structural refactor
    because it previously lived in the application entrypoint. A later audio
    service extraction can move provider-specific TTS behavior out of transport.
    """
    try:
        os.makedirs(
            "workspace/audio_cache",
            exist_ok=True,
        )

        file_path = os.path.join(
            "workspace/audio_cache",
            f"response_{int(datetime.now().timestamp())}.mp3",
        )

        communicate = edge_tts.Communicate(
            text,
            "it-IT-ElsaNeural",
        )

        await communicate.save(file_path)

        with open(file_path, "rb") as file_handle:
            base64_data = base64.b64encode(
                file_handle.read()
            ).decode("utf-8")

        if os.path.exists(file_path):
            os.remove(file_path)

        return base64_data

    except Exception as exc:
        print(f"TTS Error: {exc}")
        return ""


# ==============================================================================
# SERVER-SENT EVENTS
# ==============================================================================


# A comment line every so often keeps proxies from closing an idle stream and
# lets the server notice a closed tab without waiting for the next event.
SSE_KEEPALIVE_SECONDS = 15.0


async def sse_event_generator(
    queue: asyncio.Queue,
    request: Request,
    release,
):
    """
    Yield EventBus messages from a subscribed queue until the client leaves.

    The EventBus is used only for transient event delivery. Durable execution
    state remains owned by the Agent Engine persistence layer.
    """
    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                message = await asyncio.wait_for(
                    queue.get(),
                    timeout=SSE_KEEPALIVE_SECONDS,
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue

            yield f"data: {message}\n\n"

    finally:
        release()


@router.get("/api/events")
async def get_events_stream(
    request: Request,
    scope: Literal["session", "workspace"] = "session",
):
    """
    Open an authenticated SSE stream for realtime application events.

    - scope=session (default): the login session, the same id the WebSocket
      channel uses for its runs;
    - scope=workspace: run states and approvals of every session of the
      caller's workspace, for the Control Plane.
    """
    from app.core.db import SessionLocal
    from app.core.security import resolve_session

    try:
        with SessionLocal() as db:
            session = resolve_session(
                request,
                db,
            )
            session_id = session.id
            workspace_id = session.workspace_id
    except Exception:
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Unauthorized",
            },
        )

    if scope == "workspace":
        if not workspace_id:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "The session has no workspace.",
                },
            )

        queue = event_bus.subscribe_workspace(workspace_id)

        def release():
            event_bus.unsubscribe_workspace(workspace_id, queue)
    else:
        queue = event_bus.subscribe(session_id)

        def release():
            event_bus.unsubscribe(session_id, queue)

    return StreamingResponse(
        sse_event_generator(
            queue,
            request,
            release,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ==============================================================================
# AUTHENTICATED WEBSOCKET ORCHESTRATOR
# ==============================================================================


@router.websocket("/ws/orchestrator")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """
    Manage the authenticated realtime orchestration channel.

    The authenticated session is resolved from the server-side session store.
    Client payloads cannot override the server-derived identity.
    """
    from app.core.db import SessionLocal
    from app.core.security import (
        SESSION_COOKIE,
        IdentityService,
        Principal,
        is_origin_allowed,
    )

    # Cross-site WebSocket hijacking: the session cookie is sent by the
    # browser to any page, so the Origin must be one of ours.
    if not is_origin_allowed(
        websocket.headers.get("origin")
    ):
        print(
            "[ERROR] WebSocket connection from a disallowed origin blocked."
        )

        await websocket.close(
            code=1008
        )

        return

    client_token = websocket.cookies.get(
        SESSION_COOKIE
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

    # The login session (hash of its token), not the user: two logins of
    # the same user get separate run, memory and event scopes.
    authenticated_session_id = session.id

    await websocket.accept()

    print(
        "[OK] Authenticated WebSocket connection established."
    )

    async def safe_send(
        payload: dict,
    ):
        """
        Send a JSON payload while normalizing transport failures.
        """
        try:
            await websocket.send_json(
                payload
            )
        except Exception as exc:
            raise WebSocketDisconnect() from exc

    # Live run states, approvals and budget events of this session are
    # relayed as they happen ({"type": ..., "data": ...} messages).
    session_events = event_bus.subscribe(
        authenticated_session_id
    )

    async def forward_session_events():
        while True:
            message = await session_events.get()
            await websocket.send_text(
                message
            )

    forwarder = asyncio.create_task(
        forward_session_events()
    )

    try:
        while True:
            raw = await websocket.receive_text()

            payload = json.loads(
                raw
            )

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
            # Never accept a session identifier from the browser payload.
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

    finally:
        forwarder.cancel()
        event_bus.unsubscribe(
            authenticated_session_id,
            session_events,
        )


__all__ = [
    "get_events_stream",
    "process_audio_to_text",
    "process_text_to_audio",
    "router",
    "sse_event_generator",
    "websocket_endpoint",
]