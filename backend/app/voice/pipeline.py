"""
@file backend/app/voice/pipeline.py
@description The one voice path (ADR-021), shared by HTTP and WebSocket.

    audio --transcribe--> text --run(input_channel="voice")--> reply --speak--> audio

The transcript is the user's instruction: the run starts from it like from a
typed task (InputGuardrail included), marked as voice, so every HIGH-risk
action it proposes waits for approval on screen (PolicyEngine).

Speaking is best effort: without the engine or on failure the written reply
still arrives, with no audio.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Tuple

from app.voice.engines import VoiceUnavailable, speech_to_text, text_to_speech


logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024
TRANSCRIBE_TIMEOUT_SECONDS = 60.0
SPEAK_TIMEOUT_SECONDS = 30.0


class AudioTooLarge(ValueError):
    pass


async def transcribe_audio(audio: bytes) -> str:
    """
    The words in a recording; "" when nothing was said. Raises
    VoiceUnavailable when voice is off or its engine is missing.
    """
    if len(audio) > MAX_AUDIO_BYTES:
        raise AudioTooLarge(f"Recordings are limited to {MAX_AUDIO_BYTES // (1024 * 1024)} MB.")

    if not audio:
        return ""

    engine = speech_to_text()

    return await asyncio.wait_for(
        asyncio.to_thread(engine.transcribe, audio),
        timeout=TRANSCRIBE_TIMEOUT_SECONDS,
    )


async def speak(text: str) -> Tuple[str, str]:
    """
    (base64 audio, MIME type) of the reply, or ("", "") when it cannot be spoken.
    """
    if not text.strip():
        return "", ""

    try:
        engine = text_to_speech()
        audio, mime = await asyncio.wait_for(
            asyncio.to_thread(engine.synthesize, text),
            timeout=SPEAK_TIMEOUT_SECONDS,
        )
    except VoiceUnavailable:
        return "", ""
    except Exception as exc:
        logger.warning("Speech synthesis failed: %s", exc)
        return "", ""

    return base64.b64encode(audio).decode("ascii"), mime


__all__ = ["AudioTooLarge", "MAX_AUDIO_BYTES", "speak", "transcribe_audio"]
