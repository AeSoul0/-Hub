"""
@file backend/app/core/interface.py
@description The interface of the app as Aurora and the pages see it
(ADR-034): its language, the language of the chosen voice, the warning when
the two differ, and the context the agent gets about the app itself.

- AEHUB_UI_LANGUAGE: the language of the pages, en (default) or it.
- The voice language follows the chosen voice: the locale of the Piper voice
  (it_IT-paola-medium -> it), or the language label of the ElevenLabs voice
  when its account listed one; None when it cannot be known.
- AEHUB_VOICE_LANGUAGE_WARNING: on (default) shows a notice when the voice
  and the interface speak different languages; off hides it. The notice's
  "do not show again" turns it off; IMPOSTAZIONI or Aurora turn it back on.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.runtime_config import config_value


LANGUAGE_SETTING = "AEHUB_UI_LANGUAGE"
WARNING_SETTING = "AEHUB_VOICE_LANGUAGE_WARNING"

LANGUAGES = ("en", "it")
DEFAULT_LANGUAGE = "en"

LANGUAGE_NAMES = {
    "en": "English",
    "it": "Italian",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
}

# ElevenLabs labels name a language in several ways ("it", "italian", ...).
_LABEL_CODES = {
    "en": "en", "english": "en",
    "it": "it", "italian": "it", "italiano": "it",
    "es": "es", "spanish": "es",
    "fr": "fr", "french": "fr",
    "de": "de", "german": "de",
    "pt": "pt", "portuguese": "pt",
}

# voice_id -> language code, from the last ElevenLabs voice list.
_elevenlabs_languages: Dict[str, str] = {}


def interface_language() -> str:
    value = (config_value(LANGUAGE_SETTING, DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE).strip().lower()
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def voice_warning_enabled() -> bool:
    return (config_value(WARNING_SETTING, "on") or "on").strip().lower() != "off"


def remember_elevenlabs_languages(voices: Any) -> None:
    """
    Keep the language of each listed ElevenLabs voice (ElevenLabs returns it
    among the labels), so the voice language is known without a new request.
    """
    for voice in voices or []:
        labels = voice.get("labels") if isinstance(voice, dict) else None
        if not isinstance(labels, dict):
            continue
        code = _LABEL_CODES.get(str(labels.get("language") or "").strip().lower())
        if code:
            _elevenlabs_languages[str(voice.get("voice_id") or "")] = code


def voice_language() -> Optional[str]:
    """
    The language the chosen voice speaks, or None when it cannot be known.
    """
    engine = config_value("AEHUB_TTS_ENGINE", "piper") or "piper"

    if engine == "elevenlabs":
        voice_id = config_value("AEHUB_ELEVENLABS_VOICE", "") or ""
        return _elevenlabs_languages.get(voice_id)

    voice = config_value("AEHUB_TTS_VOICE", "it_IT-paola-medium") or ""
    code = voice.split("_", 1)[0].lower()
    return code if len(code) in (2, 3) and code.isalpha() else None


def voice_enabled() -> bool:
    return (config_value("AEHUB_VOICE", "local") or "local").strip().lower() != "off"


def interface_state() -> Dict[str, Any]:
    """
    What every page needs to know, for GET /api/interface.
    """
    engine = config_value("AEHUB_TTS_ENGINE", "piper") or "piper"
    name = (
        config_value("AEHUB_ELEVENLABS_VOICE", "") if engine == "elevenlabs"
        else config_value("AEHUB_TTS_VOICE", "it_IT-paola-medium")
    ) or ""

    return {
        "language": interface_language(),
        "languages": list(LANGUAGES),
        "voice_language_warning": voice_warning_enabled(),
        "voice": {
            "enabled": voice_enabled(),
            "engine": engine,
            "name": name,
            "language": voice_language(),
        },
    }


def _name(code: Optional[str]) -> str:
    return LANGUAGE_NAMES.get(code or "", code or "unknown")


def app_context() -> str:
    """
    What Aurora knows about the app she runs in, added to the worker's
    instructions on every turn. Only trusted values: settings, no user text.
    """
    language = interface_language()
    voice = voice_language()
    voice_text = "off" if not voice_enabled() else _name(voice) if voice else "unknown language"
    warning = "on" if voice_warning_enabled() else "off"

    # Kept short: it is part of every turn of every run.
    return (
        "You are Aurora, the agent of the ÆHub app on the user's computer: the Nucleo takes commands by text "
        "or voice; the Control Plane has Approvals, Runs, Memory, Documents, Home, Tools, Skills, Security, "
        f"Voice, Settings and System. Interface: {_name(language)}. Voice: {voice_text}. "
        f"Voice language notice: {warning}. Reply in the user's language. set_interface_language and "
        "set_voice_language_warning change the interface language and the notice."
    )


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "LANGUAGE_SETTING",
    "WARNING_SETTING",
    "app_context",
    "interface_language",
    "interface_state",
    "remember_elevenlabs_languages",
    "voice_language",
    "voice_warning_enabled",
]
