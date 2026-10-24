"""
@file backend/app/agents/orchestrator.py
@description Authenticated conversational orchestration boundary.

This module handles:
- speech-oriented response sanitization,
- slash-command processing,
- authenticated text orchestration,
- authenticated voice orchestration (local speech engines, app/voice),
- multimodal input normalization.

The module delegates actual agent execution to the native Aurora facade.
A run started from speech is marked input_channel="voice" (ADR-021).
No LangChain message classes are required by this application boundary.
"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)

from app.core.event_bus import event_bus
from app.runtime.aurora import get_aurora_app
from app.voice.engines import VoiceUnavailable
from app.voice.pipeline import AudioTooLarge, MAX_AUDIO_BYTES, speak, transcribe_audio


# ==============================================================================
# APPLICATION CONFIGURATION
# ==============================================================================


load_dotenv()

router = APIRouter(
    prefix="/api/orchestrator",
    tags=["orchestrator"],
)

INPUT_CHANNELS = ("text", "voice")


# ==============================================================================
# CORE BEHAVIORAL DIRECTIVES
# ==============================================================================


AESOUL_SYSTEM_PROMPT = (
    "You are AeSoul, the artificial intelligence orchestrating and "
    "controlling the system dashboard. "
    "IDENTITY: Act as an integral part of the platform, not a generic "
    "assistant. "
    "Your primary goal is to help the user monitor and manage the system "
    "through natural conversation. "
    "Respond professionally, precisely, and be action-oriented. Always "
    "respond in Italian unless otherwise requested. "
    "ABSOLUTE RULES OF BEHAVIOR: "
    "1. DEFAULT CONCISENESS: Provide short, direct answers. Address the "
    "main request first. Avoid long explanations. "
    "2. SMART EXPANSION: Expand ONLY if the user explicitly asks, if the "
    "request is highly complex, or if brevity causes ambiguity. Dynamically "
    "adapt your length. "
    "3. NATURAL CONVERSATION: Be fluid and natural. GET STRAIGHT TO THE "
    "POINT. NEVER use generic AI filler phrases like 'Certainly', "
    "'I am happy to help', 'Here is your answer', or 'Let me know if you "
    "need anything else'. "
    "4. DASHBOARD ORCHESTRATION: Treat dashboard data as the absolute "
    "truth. Synthesize information instead of listing raw data. Highlight "
    "anomalies, issues, risks, and opportunities. "
    "5. DATA MANAGEMENT: Use EXCLUSIVELY the provided context. Do NOT "
    "invent or hallucinate metrics, states, or events. If a data point is "
    "missing, state it clearly. "
    "6. COMMUNICATIVE EFFICIENCY: Zero repetitions, zero useless "
    "introductions, zero superfluous conclusions. Every sentence must add "
    "value. Maintain a high signal-to-noise ratio. "
    "7. FORMATTING: NO MARKDOWN ALLOWED. Do not use asterisks, hashes, "
    "bold text, or decorative blocks. Use plain, readable text only. "
    "8. OPERATIONAL PRIORITY: 1. Data Accuracy, 2. Request Understanding, "
    "3. Synthesis, 4. Clarity, 5. Completeness. "
    "FINAL GOAL: Provide a fast, natural, dashboard-oriented conversational "
    "experience, offering only truly useful information exactly when needed."
)


# ==============================================================================
# DATA PROCESSING / SPEECH HELPERS
# ==============================================================================


def clean_text_for_speech(
    text: str,
) -> str:
    """
    Remove formatting characters and normalize whitespace for TTS output.
    """
    if not text:
        return ""

    text = re.sub(
        r"\\",
        "",
        text,
    )

    text = (
        text.replace("*", "")
        .replace("#", "")
        .replace("_", "")
        .replace("[", "")
        .replace("]", "")
        .replace("`", "")
    )

    text = text.replace(
        "\n",
        ". ",
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


# ==============================================================================
# SLASH COMMAND PROCESSING
# ==============================================================================


async def execute_slash_command(
    cmd: str,
    session_id: str,
) -> dict[str, str]:
    """
    Execute a slash command. Only /stop exists: /clear, /precise, /creative,
    /deep and /fast wrote session settings nobody read, so they never had an
    effect and were removed with the legacy database module (M15). To stop a
    running agent, use Stop on the Runs page (the kill switch).
    """
    del session_id
    cmd = cmd.lower().strip()

    if cmd == "/stop":
        return {
            "transcription": (
                "[Sistema: Operazione interrotta. "
                "In attesa di istruzioni.]"
            ),
            "audio_base64": "",
        }

    return {
        "transcription": "Comando sconosciuto. Direttive accettate: stop.",
        "audio_base64": "",
    }


# ==============================================================================
# MAIN ORCHESTRATION PROCESSOR
# ==============================================================================


async def generate_ai_response(
    user_intent: str | list,
    system_prompt: str,
    ui_context: str,
    session_id: str,
    principal: Optional[Any] = None,
    input_channel: str = "text",
) -> dict[str, str]:
    """
    Delegate an authenticated interaction to the native Aurora runtime.

    input_channel is "voice" when the intent is a transcript (ADR-021).

    The caller must provide an explicit Principal. The principal is preserved
    unchanged through the compatibility facade and native AgentRuntime.
    """
    if isinstance(
        user_intent,
        list,
    ):
        if not user_intent:
            raise ValueError(
                "User intent cannot be empty."
            )

        first_item = user_intent[0]

        if isinstance(
            first_item,
            dict,
        ):
            intent_str = str(
                first_item.get(
                    "text",
                    "",
                )
            )
        else:
            intent_str = str(
                first_item
            )
    else:
        intent_str = str(
            user_intent
        )

    if not intent_str.strip():
        raise ValueError(
            "User intent cannot be empty."
        )

    if principal is None:
        raise ValueError(
            "Missing principal. Execution denied."
        )

    if input_channel not in INPUT_CHANNELS:
        raise ValueError(
            f"Unknown input channel '{input_channel}'."
        )

    del ui_context

    await event_bus.publish(
        session_id,
        "log",
        (
            "[System] Routing intent to "
            "A.U.R.O.R.A. Core: "
            f"{intent_str[:30]}..."
        ),
    )

    initial_state = {
        "messages": [
            {
                "role": "user",
                "content": intent_str,
            }
        ],
        "session_id": session_id,
        "current_intent": intent_str,
        "principal": principal,
        "system_prompt": system_prompt,
        "input_channel": input_channel,
    }

    try:
        app_instance = await get_aurora_app()

        final_state = await asyncio.wait_for(
            app_instance.ainvoke(
                initial_state,
                config={
                    "configurable": {
                        "thread_id": session_id,
                    },
                    "recursion_limit": 15,
                },
            ),
            timeout=45.0,
        )

        messages = final_state.get(
            "messages",
            [],
        )

        if not messages:
            raise RuntimeError(
                "Aurora runtime returned no messages."
            )

        last_message = messages[-1]

        if isinstance(
            last_message,
            dict,
        ):
            ai_response_text = str(
                last_message.get(
                    "content",
                    "",
                )
            )
        else:
            ai_response_text = str(
                getattr(
                    last_message,
                    "content",
                    last_message,
                )
            )

    except Exception as exc:
        print(
            f"Aurora runtime execution error: {exc}"
        )
        raise

    clean_response = clean_text_for_speech(
        ai_response_text
    )

    # Best effort: without the speech engine the written reply still arrives.
    base64_audio, audio_mime = await speak(
        clean_response
    )

    return {
        "transcription": clean_response,
        "audio_base64": base64_audio,
        "audio_mime": audio_mime,
    }


# ==============================================================================
# VOICE ENDPOINT
# ==============================================================================


@router.post("/listen")
async def process_orchestration_voice(
    request: Request,
    file: UploadFile = File(...),
    ui_context: str = Form(default=""),
    x_session_id: str = Header(
        default="default-session"
    ),
):
    """
    Authenticate the request, transcribe the audio locally and execute
    Aurora with the transcript as a voice instruction.

    The client-provided X-Session-ID header is intentionally ignored.
    Session identity is derived from the authenticated Principal.
    """
    del x_session_id

    from app.core.db import SessionLocal
    from app.core.security import resolve_principal

    with SessionLocal() as db:
        principal = resolve_principal(
            request,
            db,
        )

    audio_bytes = await file.read(
        MAX_AUDIO_BYTES + 1
    )

    try:
        transcript = await transcribe_audio(
            audio_bytes
        )
    except AudioTooLarge as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc
    except VoiceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {exc}",
        ) from exc

    if not transcript:
        return {
            "heard": "",
            "transcription": "",
            "audio_base64": "",
            "audio_mime": "",
        }

    try:
        reply = await generate_ai_response(
            transcript,
            AESOUL_SYSTEM_PROMPT,
            ui_context,
            principal.id,
            principal,
            input_channel="voice",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Voice node failure: {exc}",
        ) from exc

    return {
        "heard": transcript,
        **reply,
    }


# ==============================================================================
# TEXT / MULTIMODAL ENDPOINT
# ==============================================================================


@router.post("/ask")
async def process_orchestration_text(
    request: Request,
    text: str = Form(...),
    ui_context: str = Form(default=""),
    image: UploadFile = File(default=None),
    x_session_id: str = Header(
        default="default-session"
    ),
):
    """
    Authenticate the request and execute text or multimodal Aurora input.

    The client-provided X-Session-ID header is intentionally ignored.
    """
    del x_session_id

    try:
        from app.core.db import SessionLocal
        from app.core.security import resolve_principal

        with SessionLocal() as db:
            principal = resolve_principal(
                request,
                db,
            )

        if text.strip().startswith("/"):
            return await execute_slash_command(
                text,
                principal.id,
            )

        if image:
            image_bytes = await image.read()

            img_b64 = base64.b64encode(
                image_bytes
            ).decode("utf-8")

            text = [
                {
                    "type": "text",
                    "text": text,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{image.content_type};"
                            f"base64,{img_b64}"
                        )
                    },
                },
            ]

        return await generate_ai_response(
            text,
            AESOUL_SYSTEM_PROMPT,
            ui_context,
            principal.id,
            principal,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Text node failure: {exc}",
        ) from exc


__all__ = [
    "AESOUL_SYSTEM_PROMPT",
    "execute_slash_command",
    "generate_ai_response",
    "process_orchestration_text",
    "process_orchestration_voice",
    "router",
]