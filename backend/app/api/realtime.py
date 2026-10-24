"""
@file backend/app/api/realtime.py
@description Realtime transport boundary for SSE and WebSocket.

This module isolates transport-specific concerns from the FastAPI application
composition root. It owns authenticated realtime endpoints while delegating
speech to app.voice (local engines, ADR-021) and conversational execution to
the existing orchestration service.

Architectural boundary:
- HTTP/SSE/WebSocket transport is handled here.
- Authentication context is resolved here for transport-specific channels.
- Agent execution remains delegated to app.agents.orchestrator.
- No orchestration state or business policy is owned by this module.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from typing import Literal

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.event_bus import event_bus
from app.voice.engines import VoiceUnavailable
from app.voice.pipeline import AudioTooLarge, transcribe_audio


router = APIRouter(tags=["realtime"])


# ==============================================================================
# SERVER-SIDE AUDIO HELPERS
# ==============================================================================


def decode_audio_payload(data: str) -> bytes:
    """
    The bytes of a base64 recording, with or without a data: URL prefix.
    """
    if "," in data:
        data = data.split(",", 1)[1]

    return base64.b64decode(data, validate=True)


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

            input_channel = "text"

            if input_type == "audio_input":
                # A failed transcription is reported to the client; its
                # message must never become the agent's task.
                try:
                    user_text = await transcribe_audio(
                        decode_audio_payload(
                            str(payload.get("data", ""))
                        )
                    )
                except (VoiceUnavailable, AudioTooLarge) as exc:
                    await safe_send({"type": "error", "data": str(exc)})
                    continue
                except (binascii.Error, ValueError):
                    await safe_send({"type": "error", "data": "Invalid audio payload."})
                    continue
                except Exception as exc:
                    await safe_send({"type": "error", "data": f"Transcription failed: {exc}"})
                    continue

                input_channel = "voice"

                if user_text:
                    await safe_send({"type": "heard", "data": user_text})
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
                    input_channel=input_channel,
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
                        "mime": response_payload.get(
                            "audio_mime",
                            "",
                        ),
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
    "decode_audio_payload",
    "get_events_stream",
    "router",
    "sse_event_generator",
    "websocket_endpoint",
]