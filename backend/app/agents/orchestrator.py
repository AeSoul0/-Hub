"""
@file backend/app/agents/orchestrator.py
@description Authenticated conversational orchestration boundary.

This module handles:
- speech-oriented response sanitization,
- slash-command processing,
- authenticated text orchestration,
- authenticated voice orchestration,
- multimodal input normalization.

The module delegates actual agent execution to the native Aurora facade.
No LangChain message classes are required by this application boundary.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from typing import Any, Optional

import edge_tts
import httpx
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
from groq import AsyncGroq

from app.core import database
from app.core.event_bus import event_bus
from app.runtime.aurora import get_aurora_app


# ==============================================================================
# APPLICATION CONFIGURATION
# ==============================================================================


load_dotenv()

router = APIRouter(
    prefix="/api/orchestrator",
    tags=["orchestrator"],
)

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

if not GROQ_API_KEY:
    raise RuntimeError(
        "CRITICAL CORE CONFIGURATION FAULT: "
        "'GROQ_API_KEY' is missing from the environment."
    )

groq_client = AsyncGroq(
    api_key=GROQ_API_KEY
)


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


async def generate_voice_base64(
    text: str,
) -> str:
    """
    Convert text to speech and return the audio payload as Base64.
    """
    communicate = edge_tts.Communicate(
        text,
        "it-IT-ElsaNeural",
    )

    tts_audio_data = b""

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            tts_audio_data += chunk["data"]

    return base64.b64encode(
        tts_audio_data
    ).decode("utf-8")


# ==============================================================================
# SLASH COMMAND PROCESSING
# ==============================================================================


async def execute_slash_command(
    cmd: str,
    session_id: str,
) -> dict[str, str]:
    """
    Execute a supported slash command against the authenticated session state.
    """
    cmd = cmd.lower().strip()

    if cmd == "/stop":
        return {
            "transcription": (
                "[Sistema: Operazione interrotta. "
                "In attesa di istruzioni.]"
            ),
            "audio_base64": "",
        }

    if cmd == "/clear":
        database.clear_chat(
            session_id
        )
        reply_text = (
            "Memoria di sistema inizializzata. "
            "Cronologia cancellata."
        )

    elif cmd == "/precise":
        database.update_settings(
            session_id,
            temperature=0.1,
        )
        reply_text = (
            "Modalità precisione attivata. "
            "Varianza logica ridotta al minimo."
        )

    elif cmd == "/creative":
        database.update_settings(
            session_id,
            temperature=0.9,
        )
        reply_text = (
            "Modalità creativa ingaggiata. "
            "Reti neurali espanse."
        )

    elif cmd == "/deep":
        database.update_settings(
            session_id,
            max_tokens=1024,
            deep_mode=True,
        )
        reply_text = (
            "Analisi profonda abilitata. "
            "Parametri di sintesi disattivati."
        )

    elif cmd == "/fast":
        database.update_settings(
            session_id,
            temperature=0.75,
            max_tokens=300,
            deep_mode=False,
        )
        reply_text = (
            "Operatività rapida ingaggiata. "
            "Parametri standard ripristinati."
        )

    else:
        reply_text = (
            "Comando sconosciuto. Direttive accettate: "
            "stop, clear, precise, creative, deep, fast."
        )

    base64_audio = await generate_voice_base64(
        reply_text
    )

    return {
        "transcription": reply_text,
        "audio_base64": base64_audio,
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
) -> dict[str, str]:
    """
    Delegate an authenticated interaction to the native Aurora runtime.

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

    session_settings = database.get_settings(
        session_id
    )

    del session_settings
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
    }

    try:
        import asyncio

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

    base64_audio = await generate_voice_base64(
        clean_response
    )

    database.save_chat(
        session_id,
        intent_str,
        clean_response,
    )

    return {
        "transcription": clean_response,
        "audio_base64": base64_audio,
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
    Authenticate the request, transcribe the audio, and execute Aurora.

    The client-provided X-Session-ID header is intentionally ignored.
    Session identity is derived from the authenticated Principal.
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

        audio_bytes = await file.read()

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".webm",
            ) as temp:
                temp.write(
                    audio_bytes
                )
                temp_path = temp.name

            async with httpx.AsyncClient(
                timeout=30.0
            ) as client:
                with open(
                    temp_path,
                    "rb",
                ) as file_handle:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
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
                                f"Bearer {GROQ_API_KEY}"
                            )
                        },
                    )

            user_intent = (
                response.json().get(
                    "text",
                    "",
                )
                if response.status_code == 200
                else ""
            )

        finally:
            if (
                temp_path
                and os.path.exists(temp_path)
            ):
                os.remove(temp_path)

        if (
            not user_intent
            or user_intent == "Transcription error."
        ):
            return {
                "transcription": "",
                "audio_base64": "",
            }

        return await generate_ai_response(
            user_intent,
            AESOUL_SYSTEM_PROMPT,
            ui_context,
            principal.id,
            principal,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Voice node failure: {exc}",
        ) from exc


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