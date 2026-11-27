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
"""

from __future__ import annotations

import logging

import asyncio
import base64
import os
import re
from contextvars import ContextVar
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


logger = logging.getLogger(__name__)


# How long a command may take before the answer gives up: models on a CPU
# (Ollama in a codespace) need minutes, so it can be raised.
ANSWER_TIMEOUT_SECONDS = 45.0


def _answer_timeout() -> float:
    try:
        value = float(os.getenv("AEHUB_ANSWER_TIMEOUT_SECONDS", ""))
    except ValueError:
        return ANSWER_TIMEOUT_SECONDS
    return value if value > 0 else ANSWER_TIMEOUT_SECONDS


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
) -> dict[str, Any]:
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


# "live" delivery (N1, ADR-040): the Nucleo shows the draft while the model
# writes and speaks the accepted answer sentence by sentence itself, so the
# reply carries no audio.
DELIVERIES = ("full", "live")
_live: ContextVar[bool] = ContextVar("aehub_live_delivery", default=False)
# The Nucleo's id of a live command: its drafts and its end carry it, so
# commands sent one after another, still running together, are told apart.
_command: ContextVar[str] = ContextVar("aehub_command_id", default="")
_COMMAND_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def command_id_of(raw: str) -> str:
    """A command id from the page, or "" when it is not one."""
    return raw if _COMMAND_ID.fullmatch(raw or "") else ""


async def _voice(text: str) -> tuple[str, str]:
    """The reply spoken here, or nothing when the Nucleo speaks it sentence by sentence."""
    if _live.get():
        return "", ""
    return await speak(text)


async def _instant_reply(
    text: str,
    principal: Any,
    session_id: str,
    input_channel: str,
) -> Optional[dict[str, Any]]:
    """The reply of an instant command, or None to go on with the engine."""
    from app.instant.runner import try_instant

    try:
        instant = await try_instant(text, principal, session_id, input_channel)
    except Exception:  # noqa: BLE001 - the fast path must never cost the command: the engine takes it
        logger.exception("Instant command failed before running; the engine takes it")
        return None
    if instant is None:
        return None

    await event_bus.publish(
        session_id,
        "log",
        f"[System] Instant command {instant['tool']} in {instant['ms']} ms",
    )
    reply = clean_text_for_speech(instant["text"])
    base64_audio, audio_mime = await _voice(reply)
    return {
        "transcription": reply,
        "audio_base64": base64_audio,
        "audio_mime": audio_mime,
        "instant": {
            "tool": instant["tool"],
            "ms": instant["ms"],
            "success": instant["success"],
        },
    }


async def _decision_reply(
    text: str,
    principal: Any,
    session_id: str,
) -> Optional[dict[str, Any]]:
    """A few words when the text decides a pending approval, else None."""
    from app.core.interface import interface_language
    from app.instant.approvals import try_decision

    try:
        decided = await try_decision(text, principal, interface_language())
    except Exception:  # noqa: BLE001 - a failed check must never cost the command: the engine takes it
        logger.exception("Approval answer failed; the engine takes the text")
        return None
    if decided is None:
        return None

    await event_bus.publish(
        session_id,
        "log",
        f"[System] Approval {decided['decision'] or 'closed'} in a word, {decided['ms']} ms",
    )
    base64_audio, audio_mime = await _voice(decided["text"])
    return {
        "transcription": decided["text"],
        "audio_base64": base64_audio,
        "audio_mime": audio_mime,
        "instant": {"tool": "approval", "ms": decided["ms"], "success": decided["decision"] is not None},
        "decision": decided["decision"],
    }


async def _parked_question(content: Any, principal: Any) -> Optional[str]:
    """The short question of a run that stopped on an approval, else None."""
    if not (isinstance(content, dict) and content.get("status") == "WAITING_APPROVAL"):
        return None
    from app.core.interface import interface_language
    from app.instant.approvals import question_for_run, waiting_question

    language = interface_language()
    try:
        question = await question_for_run(str(content.get("run_id") or ""), principal, language)
    except Exception:  # noqa: BLE001 - the generic question still tells the user to decide
        logger.exception("Question of the parked run not built")
        question = None
    return question or waiting_question(language)


_STOPPED = {
    "it": {
        "CANCELLED": "Comando fermato.",
        "KILL": "Comando fermato dallo stop generale.",
        "LIMIT_EXCEEDED": "Comando fermato: ha superato un limite della run ({reason}).",
        "BUDGET_EXCEEDED": "Comando fermato: budget raggiunto ({reason}).",
    },
    "en": {
        "CANCELLED": "Command stopped.",
        "KILL": "Command stopped by the global stop.",
        "LIMIT_EXCEEDED": "Command stopped: it went over a run limit ({reason}).",
        "BUDGET_EXCEEDED": "Command stopped: budget reached ({reason}).",
    },
}


def _stopped_note(content: Any) -> Optional[str]:
    """
    One line for a run that was stopped (by you, the global stop, a limit or
    the budget), instead of the run's raw state as the answer.
    """
    if not isinstance(content, dict):
        return None
    status = str(content.get("status") or "")
    if status not in ("CANCELLED", "LIMIT_EXCEEDED", "BUDGET_EXCEEDED"):
        return None
    from app.core.interface import interface_language

    texts = _STOPPED.get(interface_language(), _STOPPED["it"])
    reason = str(content.get("reason") or "")
    if status == "CANCELLED" and "kill switch" in reason.lower():
        return texts["KILL"]
    return texts[status].format(reason=reason)


async def _publish_outcome(args: tuple, kwargs: dict, event_type: str, data: dict) -> None:
    """
    The end of a live command on the workspace channel: the Nucleo still
    gets the answer (answer.final) or the error (answer.failed) when the
    HTTP request was cut first, as GitHub's port forwarding does after about
    a minute while a model on a CPU is still writing.
    """
    session_id = kwargs.get("session_id", args[3] if len(args) > 3 else "")
    principal = kwargs.get("principal", args[4] if len(args) > 4 else None)
    if _command.get():
        data = {**data, "command_id": _command.get()}
    if event_type == "answer.final" and kwargs.get("input_channel") == "voice" and args:
        # What was heard, for a voice command whose request was cut.
        data = {**data, "heard": str(args[0])}
    try:
        await event_bus.publish(
            str(session_id or ""),
            event_type,
            data,
            workspace_id=getattr(principal, "workspace_id", "") or "",
        )
    except Exception:  # noqa: BLE001 - the HTTP reply still carries the answer
        logger.warning("The %s event of a live command was not published.", event_type)


async def generate_ai_response(
    *args: Any, delivery: str = "full", command_id: str = "", **kwargs: Any
) -> dict[str, Any]:
    """
    See _generate_ai_response; "live" delivery opens the draft and leaves
    the voice to the Nucleo. command_id is the page's id of a live command:
    its drafts and its end carry it.
    """
    if delivery not in DELIVERIES:
        raise ValueError(f"Unknown delivery '{delivery}'.")
    live = delivery == "live"
    token = _live.set(live)
    command_token = _command.set(command_id_of(command_id) if live else "")
    try:
        try:
            reply = await _generate_ai_response(*args, delivery=delivery, **kwargs)
        except Exception as exc:
            if live:
                await _publish_outcome(args, kwargs, "answer.failed", {"detail": str(exc)})
            raise
        if live:
            reply["speak"] = "sentences"
            # Without the audio: the Nucleo speaks the text itself.
            await _publish_outcome(
                args,
                kwargs,
                "answer.final",
                {"reply": {key: value for key, value in reply.items() if key not in ("audio_base64", "audio_mime")}},
            )
        return reply
    finally:
        _live.reset(token)
        _command.reset(command_token)


async def _generate_ai_response(
    user_intent: str | list,
    system_prompt: str,
    ui_context: str,
    session_id: str,
    principal: Optional[Any] = None,
    input_channel: str = "text",
    role: Optional[str] = None,
    delivery: str = "full",
) -> dict[str, Any]:
    """
    Delegate an authenticated interaction to the native Aurora runtime.

    delivery "live" (N1): a draft of the answer is published while the model
    writes, and the reply has no audio: the Nucleo speaks it sentence by
    sentence. "full": the reply carries the spoken answer, as before.

    input_channel is "voice" when the intent is a transcript (ADR-021).
    role is the worker role chosen for this command (F8); None lets triage
    pick.

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

    # ADR-037: while an approval waits, "sì" or "no" decides it at once.
    # V1 (ADR-035): a simple command ("apri Spotify", "accendi la luce della
    # cucina") runs at once, without the engine. Anything else returns None.
    if isinstance(user_intent, str):
        decided = await _decision_reply(intent_str, principal, session_id)
        if decided is not None:
            return decided
        instant = await _instant_reply(intent_str, principal, session_id, input_channel)
        if instant is not None:
            return instant

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
        "role": role,
    }

    from app.agent_engine.streaming import DraftStream, streaming_answer

    draft = (
        DraftStream(session_id, getattr(principal, "workspace_id", "") or "", _command.get())
        if delivery == "live"
        else None
    )

    try:
        app_instance = await get_aurora_app()

        with streaming_answer(draft):
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
                timeout=_answer_timeout(),
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

        # A run waiting on the owner answers with one short question
        # (ADR-037), not with its state.
        question = await _parked_question(getattr(last_message, "content", None), principal)
        if question is not None:
            base64_audio, audio_mime = await _voice(question)
            return {
                "transcription": question,
                "audio_base64": base64_audio,
                "audio_mime": audio_mime,
                "awaiting_approval": True,
            }

        # A stopped run: a line saying so, not its state as the answer.
        stopped = _stopped_note(
            last_message.get("content") if isinstance(last_message, dict) else getattr(last_message, "content", None)
        )
        if stopped is not None:
            return {"transcription": "", "audio_base64": "", "audio_mime": "", "stopped": stopped}

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

    except Exception:
        logger.exception("Aurora runtime execution error")
        raise

    clean_response = clean_text_for_speech(
        ai_response_text
    )

    # Best effort: without the speech engine the written reply still arrives.
    base64_audio, audio_mime = await _voice(
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
    delivery: str = Form(default="full"),
    command_id: str = Form(default=""),
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
            delivery=delivery if delivery in DELIVERIES else "full",
            command_id=command_id,
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
    role: str = Form(default=""),
    delivery: str = Form(default="full"),
    command_id: str = Form(default=""),
    image: UploadFile = File(default=None),
    x_session_id: str = Header(
        default="default-session"
    ),
):
    """
    Authenticate the request and execute text or multimodal Aurora input.

    The client-provided X-Session-ID header is intentionally ignored.
    `role` picks the worker role for this command (F8); empty lets triage
    pick.
    """
    del x_session_id

    from app.agent_engine.routing import command_role

    try:
        command_role(role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
            role=role or None,
            delivery=delivery if delivery in DELIVERIES else "full",
            command_id=command_id,
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