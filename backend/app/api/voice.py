"""
@file backend/app/api/voice.py
@description Authenticated real-time voice streaming endpoint.

This module provides local speech-to-text, text-to-speech, and A.U.R.O.R.A.
voice orchestration through a FastAPI WebSocket.

Security requirements:
- The WebSocket must be authenticated through a valid application session.
- The authenticated user's actual role and workspace must be preserved.
- No request may silently fall back to a synthetic "default" workspace.
- Each voice connection receives a unique runtime session identifier so
  concurrent connections do not share mutable execution state.
"""

from __future__ import annotations

import base64
import os
import tempfile
import uuid
from typing import Optional

import edge_tts
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

from app.core.db import SessionLocal
from app.core.security import IdentityService, Principal, RoleEnum


router = APIRouter(
    prefix="/api/voice",
    tags=["voice"],
)

# Lazily initialized STT model to avoid allocating model memory when voice
# functionality is not used.
_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    """
    Return the lazily initialized speech-to-text model.
    """
    global _whisper_model

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            "small",
            device="cpu",
            compute_type="int8",
        )

    return _whisper_model


def _principal_from_session(session) -> Optional[Principal]:
    """
    Convert a validated persistence session into the runtime Principal.

    The workspace and role are taken from the authenticated session record.
    No fallback identity is permitted.
    """
    if session is None:
        return None

    try:
        role = (
            session.role
            if isinstance(session.role, RoleEnum)
            else RoleEnum(session.role)
        )
    except (TypeError, ValueError):
        return None

    if not session.user_id or not session.workspace_id:
        return None

    return Principal(
        id=session.user_id,
        role=role,
        workspace_id=session.workspace_id,
    )


def _new_voice_session_id() -> str:
    """
    Create a unique execution-session identifier for one WebSocket connection.
    """
    return f"voice-{uuid.uuid4().hex}"


async def professional_tts_stream(text: str) -> str:
    """
    Synthesize text into an encoded audio payload.

    The current implementation uses edge-tts. The provider remains isolated
    behind this function so a local TTS implementation can replace it later.
    """
    communicate = edge_tts.Communicate(
        text,
        "it-IT-ElsaNeural",
    )

    tts_audio_data = bytearray()

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            tts_audio_data.extend(chunk["data"])

    return base64.b64encode(tts_audio_data).decode("utf-8")


@router.websocket("/stream")
async def voice_stream_endpoint(websocket: WebSocket) -> None:
    """
    Handle one authenticated bidirectional voice connection.
    """
    from app.runtime.aurora import run_aurora_agent

    token = websocket.query_params.get("token")
    principal: Optional[Principal] = None

    if token:
        with SessionLocal() as db:
            session = IdentityService.validate_session(
                db,
                token,
            )
            principal = _principal_from_session(session)

    await websocket.accept()

    if principal is None:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Unauthorized",
            }
        )
        await websocket.close(
            code=1008,
        )
        return

    # Never reuse a fixed "default" runtime session. A unique identifier
    # prevents concurrent voice connections from sharing durable agent state.
    voice_session_id = _new_voice_session_id()

    await websocket.send_json(
        {
            "type": "status",
            "message": "Authenticated",
        }
    )

    model = get_whisper_model()
    audio_buffer = bytearray()

    try:
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                audio_buffer.extend(data["bytes"])
                continue

            if "text" not in data:
                continue

            message = data["text"]

            if message != "END_SPEECH":
                continue

            if not audio_buffer:
                continue

            await websocket.send_json(
                {
                    "type": "status",
                    "message": "Transcribing...",
                }
            )

            tmp_path = None

            try:
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".wav",
                ) as tmp:
                    tmp.write(audio_buffer)
                    tmp_path = tmp.name

                segments, _info = model.transcribe(
                    tmp_path,
                    beam_size=5,
                    language="it",
                )

                transcript = "".join(
                    segment.text for segment in segments
                ).strip()

            finally:
                audio_buffer.clear()

                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

            if not transcript:
                continue

            await websocket.send_json(
                {
                    "type": "transcript",
                    "text": transcript,
                }
            )
            await websocket.send_json(
                {
                    "type": "status",
                    "message": "Thinking...",
                }
            )

            final_state = await run_aurora_agent(
                voice_session_id,
                transcript,
                principal,
            )

            messages = final_state.get("messages", [])
            if not messages:
                raise RuntimeError(
                    "Voice agent returned no messages."
                )

            reply = messages[-1]
            reply_text = getattr(
                reply,
                "content",
                str(reply),
            )

            await websocket.send_json(
                {
                    "type": "reply",
                    "text": reply_text,
                }
            )
            await websocket.send_json(
                {
                    "type": "status",
                    "message": "Speaking...",
                }
            )

            tts_b64 = await professional_tts_stream(
                reply_text,
            )

            await websocket.send_json(
                {
                    "type": "audio",
                    "data": tts_b64,
                }
            )
            await websocket.send_json(
                {
                    "type": "status",
                    "message": "Listening...",
                }
            )

    except WebSocketDisconnect:
        return

    except Exception as exc:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Voice processing failed.",
            }
        )
        print(f"[Voice] Stream error: {exc}")