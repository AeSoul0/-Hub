"""
@file backend/app/voice/engines.py
@description The speech engines (ADR-021, ADR-024).

- SpeechToText: faster-whisper, model AEHUB_STT_MODEL ("base"), language
  AEHUB_STT_LANGUAGE ("it", "auto" to detect), int8 on CPU, voice-activity
  filter on.
- TextToSpeech, chosen by AEHUB_TTS_ENGINE:
  - "piper" (default): voice AEHUB_TTS_VOICE ("it_IT-paola-medium"), WAV out,
    on this machine;
  - "elevenlabs" (optional, ADR-024): voice AEHUB_ELEVENLABS_VOICE, model
    AEHUB_ELEVENLABS_MODEL, key ELEVENLABS_API_KEY; the reply text leaves the
    machine. Piper speaks whenever the cloud cannot.

The settings are read on every use (Control Plane, app.core.runtime_config):
a changed model or voice applies to the next sentence. Models are downloaded
on first use into AEHUB_VOICE_MODELS_DIR (default ~/.cache/aehub/voice).
AEHUB_VOICE=off turns voice off. Tests replace the engines with set_engines().
"""

from __future__ import annotations

import importlib.util
import io
import logging
import os
import re
import threading
import wave
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple

from app.core.runtime_config import config_value


logger = logging.getLogger(__name__)

DEFAULT_STT_MODEL = "base"
DEFAULT_STT_LANGUAGE = "it"
DEFAULT_TTS_VOICE = "it_IT-paola-medium"
DEFAULT_ELEVENLABS_MODEL = "eleven_flash_v2_5"
WAV_MIME = "audio/wav"
MP3_MIME = "audio/mpeg"

ELEVENLABS_API = "https://api.elevenlabs.io"
CLOUD_TIMEOUT_SECONDS = 20.0
# Longer replies are spoken by Piper: cost is per character, and a long
# reply is better read than listened to.
MAX_CLOUD_CHARS = 2500


class VoiceUnavailable(RuntimeError):
    pass


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> Tuple[bytes, str]: ...


def voice_enabled() -> bool:
    return os.getenv("AEHUB_VOICE", "local").strip().lower() != "off"


def models_dir() -> Path:
    configured = os.getenv("AEHUB_VOICE_MODELS_DIR", "").strip()
    folder = Path(configured) if configured else Path.home() / ".cache" / "aehub" / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def missing_packages() -> list:
    """
    The engine packages that are not installed (none in a full install).
    """
    return [
        package
        for module, package in (("faster_whisper", "faster-whisper"), ("piper", "piper-tts"))
        if importlib.util.find_spec(module) is None
    ]


def stt_config() -> Tuple[str, Optional[str]]:
    """
    (model, language) as set now; language None means "detect it".
    """
    model = config_value("AEHUB_STT_MODEL", DEFAULT_STT_MODEL) or DEFAULT_STT_MODEL
    language = config_value("AEHUB_STT_LANGUAGE", DEFAULT_STT_LANGUAGE) or ""
    return model, (None if language in {"", "auto"} else language)


def tts_config() -> Tuple[str, ...]:
    """
    The engine and its voice as set now: ("piper", voice) or
    ("elevenlabs", voice_id, model, piper voice for the fallback).
    """
    piper_voice = config_value("AEHUB_TTS_VOICE", DEFAULT_TTS_VOICE) or DEFAULT_TTS_VOICE

    if config_value("AEHUB_TTS_ENGINE", "piper") == "elevenlabs":
        return (
            "elevenlabs",
            config_value("AEHUB_ELEVENLABS_VOICE", "") or "",
            config_value("AEHUB_ELEVENLABS_MODEL", DEFAULT_ELEVENLABS_MODEL) or DEFAULT_ELEVENLABS_MODEL,
            piper_voice,
        )

    return ("piper", piper_voice)


class WhisperSTT:
    def __init__(self, model_name: str = DEFAULT_STT_MODEL, language: Optional[str] = DEFAULT_STT_LANGUAGE) -> None:
        self.model_name = model_name
        self.language = language
        self.config = (model_name, language)
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(models_dir() / "whisper"),
                )
        return self._model

    def transcribe(self, audio: bytes) -> str:
        # Any container the browser records (webm/opus, ogg, wav): faster-whisper
        # decodes it with PyAV, no system ffmpeg needed.
        segments, _info = self._load().transcribe(
            io.BytesIO(audio),
            language=self.language,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


def _ascii_path(path: Path) -> Path:
    """
    espeak-ng (inside Piper) cannot open a folder whose path is not ASCII,
    e.g. under C:\\Users\\Renée or C:\\ÆHub. On Windows the 8.3 short name is
    ASCII; failing that, a copy goes into the models folder.
    """
    if str(path).isascii():
        return path

    if os.name == "nt":
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)) and buffer.value.isascii():
            return Path(buffer.value)

    copy = models_dir() / "espeak-ng-data"
    if not copy.is_dir():
        import shutil

        shutil.copytree(path, copy)
    return copy


class PiperTTS:
    def __init__(self, voice_name: str = DEFAULT_TTS_VOICE) -> None:
        self.voice_name = voice_name
        self.config: Tuple[str, ...] = ("piper", voice_name)
        self._voice = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice
                from piper.download_voices import download_voice
                from piper.voice import ESPEAK_DATA_DIR

                folder = models_dir() / "piper"
                folder.mkdir(parents=True, exist_ok=True)
                model = folder / f"{self.voice_name}.onnx"

                if not model.is_file():
                    download_voice(self.voice_name, folder)

                self._voice = PiperVoice.load(
                    model,
                    espeak_data_dir=_ascii_path(Path(ESPEAK_DATA_DIR)),
                )
        return self._voice

    def synthesize(self, text: str) -> Tuple[bytes, str]:
        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav_file:
            self._load().synthesize_wav(text, wav_file)

        return buffer.getvalue(), WAV_MIME


class ElevenLabsTTS:
    """
    The optional cloud voice (ADR-024): the reply text goes to ElevenLabs,
    MP3 comes back. Without a key or a voice, on any failure and for a reply
    longer than MAX_CLOUD_CHARS, Piper speaks instead, so a reply is never
    silent because of the cloud.
    """

    def __init__(self, voice_id: str, model: str, fallback: TextToSpeech) -> None:
        self.voice_id = voice_id
        self.model = model
        self.fallback = fallback
        self.config: Tuple[str, ...] = ("elevenlabs", voice_id, model, getattr(fallback, "voice_name", ""))

    def synthesize_cloud(self, text: str) -> Tuple[bytes, str]:
        """
        ElevenLabs only, errors raised (the Settings preview shows them).
        """
        key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()

        if not key:
            raise VoiceUnavailable("ELEVENLABS_API_KEY is not set.")

        if not self.voice_id:
            raise VoiceUnavailable("No ElevenLabs voice is selected.")

        if len(text) > MAX_CLOUD_CHARS:
            raise VoiceUnavailable(f"Replies longer than {MAX_CLOUD_CHARS} characters are spoken by Piper.")

        import httpx

        response = httpx.post(
            f"{ELEVENLABS_API}/v1/text-to-speech/{self.voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key, "accept": MP3_MIME},
            json={"text": text, "model_id": self.model},
            timeout=CLOUD_TIMEOUT_SECONDS,
        )

        if response.status_code != 200:
            raise VoiceUnavailable(f"ElevenLabs answered {response.status_code}: {_cloud_error(response)}")

        return response.content, MP3_MIME

    def synthesize(self, text: str) -> Tuple[bytes, str]:
        try:
            return self.synthesize_cloud(text)
        except Exception as exc:
            logger.warning("ElevenLabs voice unavailable, Piper speaks instead: %s", exc)
            return self.fallback.synthesize(text)


def _cloud_error(response) -> str:
    """
    ElevenLabs' own message ({"detail": {"message": ...}}), short.
    """
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None

    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status")

    return str(detail or response.reason_phrase or "error")[:200]


def elevenlabs_voices() -> List[Dict[str, str]]:
    """
    The voices of the ElevenLabs account (id, name, a few labels), for the
    Settings page. Raises VoiceUnavailable without a key or on an error.
    """
    key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()

    if not key:
        raise VoiceUnavailable("ELEVENLABS_API_KEY is not set.")

    import httpx

    response = httpx.get(
        f"{ELEVENLABS_API}/v2/voices",
        params={"page_size": 100, "include_total_count": "false"},
        headers={"xi-api-key": key},
        timeout=CLOUD_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise VoiceUnavailable(f"ElevenLabs answered {response.status_code}: {_cloud_error(response)}")

    voices = []

    for voice in response.json().get("voices") or []:
        voice_id = str(voice.get("voice_id") or "")

        if not re.fullmatch(r"[A-Za-z0-9]{8,64}", voice_id):
            continue

        labels = voice.get("labels") if isinstance(voice.get("labels"), dict) else {}
        voices.append(
            {
                "id": voice_id,
                "name": str(voice.get("name") or voice_id)[:80],
                "labels": ", ".join(
                    str(labels[key])[:30]
                    for key in ("gender", "accent", "language", "use_case")
                    if labels.get(key)
                ),
            }
        )

    return voices


def _folder_bytes(folder: Path) -> int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def downloaded_models() -> Dict[str, List[Dict[str, object]]]:
    """
    Speech models already on disk: Whisper models (Hugging Face cache layout
    "models--<owner>--faster-whisper-<name>") and Piper voices (<name>.onnx).
    """
    root = models_dir()
    whisper = []
    piper = []

    whisper_dir = root / "whisper"
    if whisper_dir.is_dir():
        for folder in sorted(whisper_dir.glob("models--*--faster-whisper-*")):
            if folder.is_dir():
                whisper.append(
                    {"name": folder.name.split("faster-whisper-", 1)[1], "bytes": _folder_bytes(folder)}
                )

    piper_dir = root / "piper"
    if piper_dir.is_dir():
        for model in sorted(piper_dir.glob("*.onnx")):
            piper.append({"name": model.stem, "bytes": model.stat().st_size})

    return {"whisper": whisper, "piper": piper}


# Engines in use, rebuilt when their settings change; overrides set by tests.
_engines: dict = {}
_overrides: dict = {}
_engines_lock = threading.Lock()


def set_engines(stt: Optional[SpeechToText] = None, tts: Optional[TextToSpeech] = None) -> None:
    """
    Replace the engines (tests); None restores the local ones on next use.
    """
    with _engines_lock:
        _overrides["stt"] = stt
        _overrides["tts"] = tts
        _engines.clear()


def _build(kind: str, config: Tuple):
    if kind == "stt":
        return WhisperSTT(*config)

    if config[0] == "elevenlabs":
        _name, voice_id, model, piper_voice = config
        return ElevenLabsTTS(voice_id, model, fallback=PiperTTS(piper_voice))

    return PiperTTS(config[1])


def _engine(kind: str):
    if not voice_enabled():
        raise VoiceUnavailable("Voice is off (AEHUB_VOICE=off).")

    with _engines_lock:
        override = _overrides.get(kind)

        if override is not None:
            return override

        # Read on every use: a model or voice changed in Settings applies to
        # the next sentence, and the old one is let go.
        config = stt_config() if kind == "stt" else tts_config()
        engine = _engines.get(kind)

        if engine is None or engine.config != config:
            missing = missing_packages()
            if missing:
                raise VoiceUnavailable(f"Voice needs {', '.join(missing)}: pip install {' '.join(missing)}")

            engine = _build(kind, config)
            _engines[kind] = engine

    return engine


def speech_to_text() -> SpeechToText:
    return _engine("stt")


def text_to_speech() -> TextToSpeech:
    return _engine("tts")


__all__ = [
    "ElevenLabsTTS",
    "MAX_CLOUD_CHARS",
    "PiperTTS",
    "SpeechToText",
    "TextToSpeech",
    "VoiceUnavailable",
    "WAV_MIME",
    "WhisperSTT",
    "downloaded_models",
    "elevenlabs_voices",
    "missing_packages",
    "models_dir",
    "set_engines",
    "speech_to_text",
    "stt_config",
    "text_to_speech",
    "tts_config",
    "voice_enabled",
]
