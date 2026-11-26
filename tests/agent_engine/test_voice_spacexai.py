"""
@file tests/agent_engine/test_voice_spacexai.py
@description The SpaceXAI (xAI) voice (ADR-038).

- the settings: only eve and altair, only it, en and fr (never auto);
- the request: POST https://api.x.ai/v1/tts with the key as a Bearer token,
  the text, the voice, the language code and an MP3 output format;
- without a key, on an error or for a long reply Piper speaks; the preview
  raises the real error;
- /api/voice tells whether the key is set and the price; the interface
  knows the language the voice reads in; the configuration check warns
  when the key is missing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import voice as voice_api
from app.core.interface import interface_state, voice_language
from app.core.runtime_config import replace_stored
from app.core.security import Principal, resolve_principal
from app.core.settings_service import SettingsValidationError, check_configuration, validate_changes
from app.domain.models.identity import RoleEnum
from app.voice import engines

ADMIN = Principal(id="admin-owner", role=RoleEnum.ADMIN, workspace_id="workspace-1")
FAKE_KEY = "xai-test-key-not-real"


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: List[str] = []

    def synthesize(self, text: str) -> Tuple[bytes, str]:
        self.spoken.append(text)
        return b"RIFF-local", "audio/wav"


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", body: Any = None) -> None:
        self.status_code = status_code
        self.content = content
        self.reason_phrase = "Unauthorized" if status_code == 401 else "OK"
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture(autouse=True)
def clean_voice(monkeypatch, tmp_path):
    for name in ("AEHUB_TTS_ENGINE", "AEHUB_SPACEXAI_VOICE", "AEHUB_SPACEXAI_LANGUAGE", "XAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AEHUB_VOICE", "local")
    monkeypatch.setenv("AEHUB_VOICE_MODELS_DIR", str(tmp_path / "voice"))
    monkeypatch.setattr(engines, "missing_packages", lambda: [])
    replace_stored({})
    engines.set_engines()
    yield
    replace_stored({})
    engines.set_engines()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AEHUB_SPACEXAI_VOICE", "rex"),
        ("AEHUB_SPACEXAI_LANGUAGE", "auto"),
        ("AEHUB_SPACEXAI_LANGUAGE", "de"),
    ],
)
def test_only_the_two_voices_and_three_languages(name, value):
    with pytest.raises(SettingsValidationError) as refused:
        validate_changes({name: value})
    assert name in refused.value.errors


def test_the_engine_follows_the_settings():
    changes = {"AEHUB_TTS_ENGINE": "spacexai", "AEHUB_SPACEXAI_VOICE": "altair", "AEHUB_SPACEXAI_LANGUAGE": "fr"}
    assert validate_changes(changes) == changes

    replace_stored({"AEHUB_TTS_ENGINE": "spacexai"})
    default = engines.text_to_speech()
    assert isinstance(default, engines.SpaceXAITTS)
    assert (default.voice, default.language) == ("eve", "it")
    assert isinstance(default.fallback, engines.PiperTTS)

    replace_stored(changes)
    chosen = engines.text_to_speech()
    assert chosen is not default and (chosen.voice, chosen.language) == ("altair", "fr")


def test_the_request_carries_text_voice_language_and_format(monkeypatch):
    calls: List[Dict[str, Any]] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, b"ID3-mp3")

    monkeypatch.setattr("httpx.post", post)
    monkeypatch.setenv("XAI_API_KEY", FAKE_KEY)
    local = FakeTTS()
    tts = engines.SpaceXAITTS("altair", "en", fallback=local)

    assert tts.synthesize("Light on.") == (b"ID3-mp3", "audio/mpeg")
    assert local.spoken == []

    [call] = calls
    assert call["url"] == "https://api.x.ai/v1/tts"
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert call["json"] == {
        "text": "Light on.",
        "voice_id": "altair",
        "language": "en",
        "output_format": {"codec": "mp3", "sample_rate": 24000, "bit_rate": 128000},
    }
    assert call["timeout"] > 0


def test_piper_speaks_when_spacexai_cannot(monkeypatch):
    local = FakeTTS()
    tts = engines.SpaceXAITTS("eve", "it", fallback=local)
    posted: List[str] = []

    def post(url, **kwargs):
        posted.append(kwargs["json"]["text"])
        return FakeResponse(401, body={"error": "Incorrect API key provided"})

    monkeypatch.setattr("httpx.post", post)

    # No key: nothing leaves the machine.
    assert tts.synthesize("uno") == (b"RIFF-local", "audio/wav")
    assert posted == []

    monkeypatch.setenv("XAI_API_KEY", FAKE_KEY)
    assert tts.synthesize("due") == (b"RIFF-local", "audio/wav")
    assert posted == ["due"]

    # A long reply is spoken locally, never sent (cost is per character).
    long_reply = "x" * (engines.MAX_CLOUD_CHARS + 1)
    assert tts.synthesize(long_reply) == (b"RIFF-local", "audio/wav")
    assert posted == ["due"]
    assert local.spoken == ["uno", "due", long_reply]

    with pytest.raises(engines.VoiceUnavailable, match="401: Incorrect API key provided"):
        tts.synthesize_cloud("tre")


def test_status_interface_and_check(monkeypatch):
    replace_stored({"AEHUB_TTS_ENGINE": "spacexai", "AEHUB_SPACEXAI_VOICE": "altair", "AEHUB_SPACEXAI_LANGUAGE": "en"})

    app = FastAPI()
    app.include_router(voice_api.router)
    app.dependency_overrides[resolve_principal] = lambda: ADMIN
    status = TestClient(app).get("/api/voice").json()["tts"]
    assert status["engine"] == "spacexai"
    assert status["spacexai_key"] is False
    assert status["spacexai_usd_per_million_chars"] == 15.0
    assert status["piper_voice"] == "it_IT-paola-medium"

    assert voice_language() == "en"
    assert interface_state()["voice"]["name"] == "altair"

    codes = {issue.code for issue in check_configuration()}
    assert "voice_spacexai_key_missing" in codes
    monkeypatch.setenv("XAI_API_KEY", FAKE_KEY)
    assert "voice_spacexai_key_missing" not in {issue.code for issue in check_configuration()}
