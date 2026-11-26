"""
@file tests/agent_engine/test_wake_word.py
@description N2 (ADR-041): the wake word models the Nucleo listens with.

- the settings: off by default, three ready-made words and "aurora" (your
  own model), three sensitivities;
- the models come from the openWakeWord release, are checked against their
  SHA-256 before they are kept or served, and are downloaded once;
- /api/voice/wake serves only the feature models and the chosen word;
  "aurora" is your file, and without it the answer says where to put it;
- the interface tells every page the word, its name and the threshold; the
  configuration check warns when aurora is chosen without its model.
"""

from __future__ import annotations

import hashlib
from typing import List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import voice as voice_api
from app.core.interface import interface_state
from app.core.runtime_config import replace_stored
from app.core.security import Principal, resolve_principal
from app.core.settings_service import SettingsValidationError, check_configuration, validate_changes
from app.domain.models.identity import RoleEnum
from app.voice import wake

ADMIN = Principal(id="admin-owner", role=RoleEnum.ADMIN, workspace_id="workspace-1")


@pytest.fixture
def models(monkeypatch, tmp_path) -> List[str]:
    """The release, faked: each file holds its own name; the pins match those bytes."""
    monkeypatch.setenv("AEHUB_VOICE_MODELS_DIR", str(tmp_path / "voice"))
    fetched: List[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return url.rsplit("/", 1)[-1].encode()

    pins = {
        name: {"file": pinned["file"], "sha256": hashlib.sha256(pinned["file"].encode()).hexdigest()}
        for name, pinned in wake.PINNED.items()
    }
    monkeypatch.setattr(wake, "PINNED", pins)
    monkeypatch.setattr(wake, "_fetch", fetch)
    replace_stored({})
    yield fetched
    replace_stored({})


def client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_api.router)
    app.dependency_overrides[resolve_principal] = lambda: ADMIN
    return TestClient(app)


def test_the_settings():
    assert wake.wake_word() == "off"
    changes = {"AEHUB_WAKE_WORD": "hey_jarvis", "AEHUB_WAKE_SENSITIVITY": "high"}
    assert validate_changes(changes) == changes
    for name, value in (("AEHUB_WAKE_WORD", "ok_google"), ("AEHUB_WAKE_SENSITIVITY", "max")):
        with pytest.raises(SettingsValidationError) as refused:
            validate_changes({name: value})
        assert name in refused.value.errors


def test_the_pins_are_the_release_files():
    # The real hashes of the v0.5.1 files, as checked when they were pinned.
    assert wake.RELEASE.endswith("/v0.5.1")
    assert wake.PINNED["hey_jarvis"] == {
        "file": "hey_jarvis_v0.1.onnx",
        "sha256": "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    }
    assert set(wake.PINNED) == {"melspectrogram", "embedding_model", "hey_jarvis", "alexa", "hey_mycroft"}
    assert all(len(pinned["sha256"]) == 64 for pinned in wake.PINNED.values())


def test_downloaded_once_and_checked(models, monkeypatch):
    path = wake.model_path("hey_jarvis")
    assert path.read_bytes() == b"hey_jarvis_v0.1.onnx"
    assert models == [f"{wake.RELEASE}/hey_jarvis_v0.1.onnx"]

    wake.model_path("hey_jarvis")
    assert len(models) == 1

    # A file changed on disk is downloaded again; a download that does not match is refused.
    path.write_bytes(b"changed")
    monkeypatch.setattr(wake, "_fetch", lambda url: b"something else")
    with pytest.raises(wake.WakeModelUnavailable, match="expected"):
        wake.model_path("hey_jarvis")
    assert path.read_bytes() == b"changed"


def test_the_endpoint_serves_only_what_is_in_use(models):
    api = client()
    assert api.get("/api/voice/wake/melspectrogram").content == b"melspectrogram.onnx"
    # The word is off: no word model is served.
    assert api.get("/api/voice/wake/hey_jarvis").status_code == 404
    assert api.get("/api/voice/wake/off").status_code == 404

    replace_stored({"AEHUB_WAKE_WORD": "alexa"})
    assert api.get("/api/voice/wake/alexa").content == b"alexa_v0.1.onnx"
    assert api.get("/api/voice/wake/hey_jarvis").status_code == 404
    assert api.get("/api/voice/wake/..%2Fsecrets").status_code == 404

    status = api.get("/api/voice").json()["wake"]
    assert status["word"] == "alexa" and status["threshold"] == 0.5
    assert status["downloaded"]["alexa"] is True and status["downloaded"]["hey_mycroft"] is False


def test_aurora_is_your_own_model(models):
    replace_stored({"AEHUB_WAKE_WORD": "aurora"})
    api = client()

    missing = api.get("/api/voice/wake/aurora")
    assert missing.status_code == 503
    assert str(wake.own_model_path()) in missing.json()["detail"]
    assert "voice_wake_model_missing" in {issue.code for issue in check_configuration()}

    wake.own_model_path().write_bytes(b"my aurora")
    assert api.get("/api/voice/wake/aurora").content == b"my aurora"
    assert models == []
    assert "voice_wake_model_missing" not in {issue.code for issue in check_configuration()}


def test_every_page_knows_the_word(models):
    assert interface_state()["wake"] == {"word": "off", "label": "", "threshold": 0.5}
    replace_stored({"AEHUB_WAKE_WORD": "hey_jarvis", "AEHUB_WAKE_SENSITIVITY": "low"})
    assert interface_state()["wake"] == {"word": "hey_jarvis", "label": "Hey Jarvis", "threshold": 0.7}
