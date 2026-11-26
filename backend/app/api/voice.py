"""
@file backend/app/api/voice.py
@description Voice for the Control Plane and the Nucleo (F3, ADR-021, ADR-024).

GET  /api/voice                    what is set and what is on disk: engines,
                                   models already downloaded, whether the
                                   ElevenLabs key is set (never its value)
GET  /api/voice/elevenlabs/voices  the voices of the ElevenLabs account
GET  /api/voice/wake/{model}        a wake word model (N2, ADR-041): the
                                   two feature models or the chosen word,
                                   downloaded once and checked (SHA-256)
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
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.security import Principal, resolve_principal
from app.voice import engines, wake
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
    # The length of the whole reply when the Nucleo speaks it sentence by
    # sentence (N1): a reply longer than the cloud limit stays with Piper,
    # as it did when it was spoken in one piece.
    reply_chars: int = Field(default=0, ge=0, le=1_000_000)


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
            "piper_voice": tts[-1] if tts[0] != "piper" else tts[1],
            "elevenlabs_voice": tts[1] if tts[0] == "elevenlabs" else "",
            "elevenlabs_key": bool((os.getenv("ELEVENLABS_API_KEY") or "").strip()),
            "spacexai_key": bool((os.getenv("XAI_API_KEY") or "").strip()),
            "spacexai_usd_per_million_chars": engines.SPACEXAI_USD_PER_MILLION_CHARS,
            "max_cloud_chars": engines.MAX_CLOUD_CHARS,
        },
        "downloaded": engines.downloaded_models(),
        "wake": {
            **wake.wake_state(),
            "own_model_path": str(wake.own_model_path()),
            "downloaded": wake.downloaded(),
        },
    }


# The feature models are always needed; of the words, only the chosen one.
FEATURE_MODELS = ("melspectrogram", "embedding_model")


@router.get("/wake/{model}")
async def wake_model(
    model: str,
    principal: Principal = Depends(resolve_principal),
) -> FileResponse:
    del principal

    if model not in FEATURE_MODELS and (model == "off" or model != wake.wake_word()):
        raise HTTPException(status_code=404, detail=f"{model} is not a wake word model in use.")

    try:
        path = await asyncio.to_thread(wake.model_path, model)
    except wake.WakeModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"The wake word model could not be downloaded: {exc}") from exc

    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "private, max-age=86400"})


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
        audio, mime = await speak(text, local=request.reply_chars > engines.MAX_CLOUD_CHARS)
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
