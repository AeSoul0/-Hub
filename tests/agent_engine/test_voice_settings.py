"""
@file tests/agent_engine/test_voice_settings.py
@description F3: voice settings from the Control Plane and the optional
ElevenLabs voice (ADR-024).

- the voice settings are checked (choices, names that end up in a path or a
  URL) and apply to the next sentence without a restart;
- ElevenLabs gets the text, the voice and the model; without a key, on an
  error or for a long reply Piper speaks instead; the preview raises;
- /api/voice: status with the models on disk, the voice list, speaking;
- the configuration check says when the cloud voice cannot be used.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import voice as voice_api
from app.core.runtime_config import replace_stored
from app.core.security import Principal, resolve_principal
from app.core.settings_service import (
    SettingsValidationError,
    check_configuration,
    validate_changes,
)
from app.domain.models.identity import RoleEnum
from app.voice import engines


ADMIN = Principal(id="admin-owner", role=RoleEnum.ADMIN, workspace_id="workspace-1")

FAKE_KEY = "el-test-key-not-real"
VOICE_ID = "Xb7hH8MSUJpSbSDYk0k2"


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
    for name in (
        "AEHUB_STT_MODEL",
        "AEHUB_STT_LANGUAGE",
        "AEHUB_TTS_ENGINE",
        "AEHUB_TTS_VOICE",
        "AEHUB_ELEVENLABS_VOICE",
        "AEHUB_ELEVENLABS_MODEL",
        "ELEVENLABS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("AEHUB_VOICE", "local")
    monkeypatch.setenv("AEHUB_VOICE_MODELS_DIR", str(tmp_path / "voice"))
    monkeypatch.setattr(engines, "missing_packages", lambda: [])
    replace_stored({})
    engines.set_engines()
    yield
    replace_stored({})
    engines.set_engines()


def voice_client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_api.router)
    app.dependency_overrides[resolve_principal] = lambda: ADMIN
    return TestClient(app)


# ==============================================================================
# SETTINGS
# ==============================================================================


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AEHUB_STT_MODEL", "huge"),
        ("AEHUB_STT_LANGUAGE", "klingon"),
        ("AEHUB_TTS_ENGINE", "cloud"),
        ("AEHUB_TTS_VOICE", "../../etc/passwd"),
        ("AEHUB_TTS_VOICE", "it_IT-paola"),
        ("AEHUB_ELEVENLABS_VOICE", "abc/../../v1/user"),
        ("AEHUB_ELEVENLABS_MODEL", "Eleven Flash"),
    ],
)
def test_invalid_voice_settings_are_refused(name, value):
    with pytest.raises(SettingsValidationError) as error:
        validate_changes({name: value})

    assert name in error.value.errors


def test_valid_voice_settings_pass():
    changes = {
        "AEHUB_STT_MODEL": "large-v3-turbo",
        "AEHUB_STT_LANGUAGE": "auto",
        "AEHUB_TTS_ENGINE": "elevenlabs",
        "AEHUB_TTS_VOICE": "en_US-lessac-medium",
        "AEHUB_ELEVENLABS_VOICE": VOICE_ID,
        "AEHUB_ELEVENLABS_MODEL": "eleven_multilingual_v2",
    }

    assert validate_changes(changes) == changes


def test_engines_follow_the_settings_without_a_restart():
    stt = engines.speech_to_text()
    assert (stt.model_name, stt.language) == ("base", "it")
    assert engines.speech_to_text() is stt

    replace_stored({"AEHUB_STT_MODEL": "small", "AEHUB_STT_LANGUAGE": "auto"})
    changed = engines.speech_to_text()
    assert changed is not stt
    assert (changed.model_name, changed.language) == ("small", None)

    tts = engines.text_to_speech()
    assert isinstance(tts, engines.PiperTTS) and tts.voice_name == "it_IT-paola-medium"

    replace_stored({"AEHUB_TTS_ENGINE": "elevenlabs", "AEHUB_ELEVENLABS_VOICE": VOICE_ID})
    cloud = engines.text_to_speech()
    assert isinstance(cloud, engines.ElevenLabsTTS)
    assert (cloud.voice_id, cloud.model) == (VOICE_ID, "eleven_flash_v2_5")
    assert isinstance(cloud.fallback, engines.PiperTTS)


# ==============================================================================
# ELEVENLABS
# ==============================================================================


def test_elevenlabs_gets_text_voice_and_model(monkeypatch):
    calls: List[Dict[str, Any]] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, b"ID3-mp3")

    monkeypatch.setattr("httpx.post", post)
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    local = FakeTTS()
    tts = engines.ElevenLabsTTS(VOICE_ID, "eleven_flash_v2_5", fallback=local)

    assert tts.synthesize("Luce accesa.") == (b"ID3-mp3", "audio/mpeg")
    assert local.spoken == []

    [call] = calls
    assert call["url"] == f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    assert call["headers"]["xi-api-key"] == FAKE_KEY
    assert call["json"] == {"text": "Luce accesa.", "model_id": "eleven_flash_v2_5"}
    assert call["timeout"] > 0


def test_piper_speaks_when_the_cloud_cannot(monkeypatch):
    local = FakeTTS()
    tts = engines.ElevenLabsTTS(VOICE_ID, "eleven_flash_v2_5", fallback=local)
    posted: List[str] = []

    def post(url, **kwargs):
        posted.append(kwargs["json"]["text"])
        return FakeResponse(401, body={"detail": {"message": "Invalid API key"}})

    monkeypatch.setattr("httpx.post", post)

    # No key: nothing leaves the machine.
    assert tts.synthesize("uno") == (b"RIFF-local", "audio/wav")
    assert posted == []

    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)

    # ElevenLabs refuses.
    assert tts.synthesize("due") == (b"RIFF-local", "audio/wav")
    assert posted == ["due"]

    # A long reply is spoken locally, never sent.
    long_reply = "x" * (engines.MAX_CLOUD_CHARS + 1)
    assert tts.synthesize(long_reply) == (b"RIFF-local", "audio/wav")
    assert posted == ["due"]
    assert local.spoken == ["uno", "due", long_reply]

    # The preview shows the real error instead.
    with pytest.raises(engines.VoiceUnavailable, match="401: Invalid API key"):
        tts.synthesize_cloud("tre")


def test_elevenlabs_voice_list_keeps_only_safe_ids(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    seen: Dict[str, Any] = {}

    def get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(
            200,
            body={
                "voices": [
                    {"voice_id": VOICE_ID, "name": "Bianca", "labels": {"gender": "female", "accent": "italian"}},
                    {"voice_id": "../bad", "name": "Bad"},
                ],
                "has_more": False,
            },
        )

    monkeypatch.setattr("httpx.get", get)

    assert engines.elevenlabs_voices() == [{"id": VOICE_ID, "name": "Bianca", "labels": "female, italian"}]
    assert seen["url"] == "https://api.elevenlabs.io/v2/voices"
    assert seen["headers"] == {"xi-api-key": FAKE_KEY}


# ==============================================================================
# HTTP
# ==============================================================================


def test_status_lists_settings_and_models_on_disk(tmp_path):
    root = tmp_path / "voice"
    whisper = root / "whisper" / "models--Systran--faster-whisper-base" / "blobs"
    whisper.mkdir(parents=True)
    (whisper / "model").write_bytes(b"w" * 300)
    (root / "piper").mkdir(parents=True)
    (root / "piper" / "it_IT-paola-medium.onnx").write_bytes(b"p" * 120)
    replace_stored({"AEHUB_STT_LANGUAGE": "auto"})

    status = voice_client().get("/api/voice").json()

    assert status["enabled"] is True and status["missing"] == []
    assert status["stt"] == {"model": "base", "language": "auto"}
    assert status["tts"]["engine"] == "piper"
    assert status["tts"]["piper_voice"] == "it_IT-paola-medium"
    assert status["tts"]["elevenlabs_key"] is False
    assert status["downloaded"] == {
        "whisper": [{"name": "base", "bytes": 300}],
        "piper": [{"name": "it_IT-paola-medium", "bytes": 120}],
    }


def test_speak_and_preview(monkeypatch):
    local = FakeTTS()
    engines.set_engines(tts=local)
    client = voice_client()

    spoken = client.post("/api/voice/speak", json={"text": "**Fatto**, garage aperto."}).json()
    assert base64.b64decode(spoken["audio_base64"]) == b"RIFF-local"
    assert local.spoken == ["Fatto, garage aperto."]

    assert client.post("/api/voice/speak", json={"text": "x" * 5001}).status_code == 422

    # The cloud preview says what is wrong instead of falling back.
    engines.set_engines()
    replace_stored({"AEHUB_TTS_ENGINE": "elevenlabs", "AEHUB_ELEVENLABS_VOICE": VOICE_ID})
    preview = client.post("/api/voice/speak", json={"text": "Ciao", "preview": True})
    assert preview.status_code == 503
    assert "ELEVENLABS_API_KEY" in preview.json()["detail"]


def test_voice_list_without_a_key():
    response = voice_client().get("/api/voice/elevenlabs/voices")

    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]


def test_configuration_check_explains_the_cloud_voice(monkeypatch):
    replace_stored({"AEHUB_TTS_ENGINE": "elevenlabs"})
    codes = {issue.code: issue.severity for issue in check_configuration()}
    assert codes.get("voice_cloud_key_missing") == "warning"

    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)
    codes = {issue.code: issue.severity for issue in check_configuration()}
    assert "voice_cloud_key_missing" not in codes
    assert codes.get("voice_cloud_voice_missing") == "warning"

    replace_stored({"AEHUB_TTS_ENGINE": "elevenlabs", "AEHUB_ELEVENLABS_VOICE": VOICE_ID})
    codes = {issue.code for issue in check_configuration()}
    assert not {"voice_cloud_key_missing", "voice_cloud_voice_missing"} & codes

