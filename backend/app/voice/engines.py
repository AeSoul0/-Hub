"""
@file backend/app/voice/engines.py
@description The local speech engines (ADR-021).

- SpeechToText: faster-whisper, model AEHUB_STT_MODEL ("base"), language
  AEHUB_STT_LANGUAGE ("it"), int8 on CPU, voice-activity filter on.
- TextToSpeech: Piper, voice AEHUB_TTS_VOICE ("it_IT-paola-medium"), WAV out.

Models are downloaded on first use into AEHUB_VOICE_MODELS_DIR (default
~/.cache/aehub/voice) and loaded once per process. AEHUB_VOICE=off turns
voice off. Tests replace the engines with set_engines().
"""

from __future__ import annotations

import importlib.util
import io
import os
import threading
import wave
from pathlib import Path
from typing import Optional, Protocol, Tuple


DEFAULT_STT_MODEL = "base"
DEFAULT_STT_LANGUAGE = "it"
DEFAULT_TTS_VOICE = "it_IT-paola-medium"
WAV_MIME = "audio/wav"


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


class WhisperSTT:
    def __init__(self) -> None:
        self.model_name = os.getenv("AEHUB_STT_MODEL", DEFAULT_STT_MODEL)
        self.language = os.getenv("AEHUB_STT_LANGUAGE", DEFAULT_STT_LANGUAGE) or None
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
    def __init__(self) -> None:
        self.voice_name = os.getenv("AEHUB_TTS_VOICE", DEFAULT_TTS_VOICE)
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


_engines: dict = {}
_engines_lock = threading.Lock()


def set_engines(stt: Optional[SpeechToText] = None, tts: Optional[TextToSpeech] = None) -> None:
    """
    Replace the engines (tests); None restores the local ones on next use.
    """
    with _engines_lock:
        _engines["stt"] = stt
        _engines["tts"] = tts


def _engine(kind: str):
    if not voice_enabled():
        raise VoiceUnavailable("Voice is off (AEHUB_VOICE=off).")

    with _engines_lock:
        engine = _engines.get(kind)

        if engine is None:
            missing = missing_packages()
            if missing:
                raise VoiceUnavailable(f"Voice needs {', '.join(missing)}: pip install {' '.join(missing)}")

            engine = WhisperSTT() if kind == "stt" else PiperTTS()
            _engines[kind] = engine

    return engine


def speech_to_text() -> SpeechToText:
    return _engine("stt")


def text_to_speech() -> TextToSpeech:
    return _engine("tts")


__all__ = [
    "PiperTTS",
    "SpeechToText",
    "TextToSpeech",
    "VoiceUnavailable",
    "WAV_MIME",
    "WhisperSTT",
    "missing_packages",
    "models_dir",
    "set_engines",
    "speech_to_text",
    "text_to_speech",
    "voice_enabled",
]
