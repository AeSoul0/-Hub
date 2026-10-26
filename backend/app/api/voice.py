"""
@file backend/app/api/voice.py
@description Voice for the Control Plane and the Nucleo (F3, ADR-021, ADR-024).

GET  /api/voice                    what is set and what is on disk: engines,
                                   models already downloaded, whether the
                                   ElevenLabs key is set (never its value)
GET  /api/voice/elevenlabs/voices  the voices of the ElevenLabs account
POST /api/voice/speak              {"text", "preview"}: the reply spoken.
                                   preview=false is best effort (the Nucleo
                                   speaking a run resumed after an approval);
                                   preview=true raises what went wrong.

The settings themselves (model, language, engine, voice) are edited through
/api/settings, group "voice"; the key through /api/desktop/secrets.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, resolve_principal
from app.voice import engines
from app.voice.pipeline import SPEAK_TIMEOUT_SECONDS, preview_voice, speak


router = APIRouter(
    prefix="/api/voice",
    tags=["voice"],
)

# A spoken reply, not a document: longer text is refused.
MAX_SPEAK_CHARS = 5000


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_SPEAK_CHARS)
    preview: bool = False


@router.get("")
async def voice_status(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del principal

    model, language = engines.stt_config()
    tts = engines.tts_config()

    return {
        "enabled": engines.voice_enabled(),
        "missing": engines.missing_packages(),
        "stt": {"model": model, "language": language or "auto"},
        "tts": {
            "engine": tts[0],
            "piper_voice": tts[-1] if tts[0] == "elevenlabs" else tts[1],
            "elevenlabs_voice": tts[1] if tts[0] == "elevenlabs" else "",
            "elevenlabs_key": bool((os.getenv("ELEVENLABS_API_KEY") or "").strip()),
            "max_cloud_chars": engines.MAX_CLOUD_CHARS,
        },
        "downloaded": engines.downloaded_models(),
    }


@router.get("/elevenlabs/voices")
async def list_elevenlabs_voices(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del principal

    try:
        voices = await asyncio.to_thread(engines.elevenlabs_voices)
    except engines.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ElevenLabs is not reachable: {exc}") from exc

    return {"voices": voices}


@router.post("/speak")
async def speak_text(
    request: SpeakRequest,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, str]:
    del principal

    from app.agents.orchestrator import clean_text_for_speech

    text = clean_text_for_speech(request.text)

    if not request.preview:
        audio, mime = await speak(text)
        return {"audio_base64": audio, "audio_mime": mime}

    try:
        audio, mime = await preview_voice(text)
    except engines.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"The voice did not answer within {SPEAK_TIMEOUT_SECONDS:g} seconds.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"The voice failed: {exc}") from exc

    return {"audio_base64": audio, "audio_mime": mime}
