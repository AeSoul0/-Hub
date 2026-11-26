"""
@file tests/agent_engine/test_instant_commands.py
@description V1 (ADR-035): simple commands run at once, without the model.

- the matcher takes only whole, known commands, in Italian and English, and
  leaves everything else (and unlocking) to the engine;
- the app list is validated like any setting;
- an app really starts, detached, and never inside a container;
- a recognized command runs through the Tool Gateway with its audit row and
  answers in the language spoken, while the engine is never started;
- turned off, unknown or in need of approval: the engine takes the command.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock

import pytest

from app.agents import orchestrator
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum
from app.core.settings_service import SettingsValidationError, validate_changes
from app.domain.models.audit import AuditLog
from app.home import mqtt
from app.home.store import forget
from app.instant import apps as apps_module
from app.instant.apps import AppConfigError, LaunchError, launch, parse_apps
from app.instant.matcher import match
from app.skills.apps_skill import AppsSkill
from app.skills.home_skill import HomeSkill


WORKSPACE = "workspace-v1"
OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id=WORKSPACE)

APPS = ["spotify", "visual studio code", "firefox"]
LIGHTS = [("kitchen", "Cucina"), ("living_room", "Soggiorno")]
LOCKS = [("front_door", "Porta di casa")]


@pytest.fixture(autouse=True)
def clean_settings():
    replace_stored({})
    forget()
    yield
    replace_stored({})
    forget()


# ==============================================================================
# MATCHER
# ==============================================================================


@pytest.mark.parametrize(
    "sentence, tool, arguments, language",
    [
        ("Apri Spotify", "open_app", {"app": "spotify"}, "it"),
        ("Aurora, per favore apri spotify", "open_app", {"app": "spotify"}, "it"),
        ("avvia l'app Firefox", "open_app", {"app": "firefox"}, "it"),
        ("apri Visual Studio Code", "open_app", {"app": "visual studio code"}, "it"),
        ("open Spotify", "open_app", {"app": "spotify"}, "en"),
        ("launch the firefox app please", "open_app", {"app": "firefox"}, "en"),
        ("Apri la cartella Download", "open_folder", {"folder": "download"}, "it"),
        ("apri i documenti", "open_folder", {"folder": "documenti"}, "it"),
        ("open the downloads folder", "open_folder", {"folder": "downloads"}, "en"),
        ("accendi la luce della cucina", "home_set_light", {"device": "kitchen", "on": True}, "it"),
        ("Spegni la luce del soggiorno", "home_set_light", {"device": "living_room", "on": False}, "it"),
        ("turn on the kitchen light", "home_set_light", {"device": "kitchen", "on": True}, "en"),
        ("turn the living room light off", "home_set_light", {"device": "living_room", "on": False}, "en"),
        ("chiudi a chiave la porta di casa", "home_lock", {"device": "front_door"}, "it"),
        ("lock the front door", "home_lock", {"device": "front_door"}, "en"),
    ],
)
def test_whole_known_commands_are_instant(sentence, tool, arguments, language):
    command = match(sentence, APPS, LIGHTS, LOCKS)

    assert command is not None
    assert (command.tool, command.arguments, command.language) == (tool, arguments, language)


@pytest.mark.parametrize(
    "sentence",
    [
        "apri Word",  # not in the list
        "apri spotify e metti la mia playlist",  # more than one thing
        "open spotify and then firefox",
        "accendi la luce del bagno",  # no such light
        "accendi la luce della cucina al 50%",  # a detail the fixed form has no slot for
        "apri la porta di casa",  # unlocking: HIGH, never instant
        "sblocca la porta di casa",
        "unlock the front door",
        "che tempo fa domani?",
        "start a war",
        "",
    ],
)
def test_anything_else_goes_to_the_engine(sentence):
    assert match(sentence, APPS, LIGHTS, LOCKS) is None


def test_the_reply_names_the_device_not_its_id():
    assert match("accendi cucina", APPS, LIGHTS, LOCKS).name == "Cucina"
    assert match("lock the front door", APPS, LIGHTS, LOCKS).name == "Porta di casa"


# ==============================================================================
# APP LIST
# ==============================================================================


def test_the_app_list_is_validated():
    assert parse_apps('{"Spotify": "spotify", "Code": ["code", "--new-window"]}') == {
        "spotify": ["spotify"],
        "code": ["code", "--new-window"],
    }
    assert parse_apps("") == {}

    for bad in ('["spotify"]', "{not json", '{"x": 3}', '{"x": ""}', '{"$$$": "a"}', '{"x": []}'):
        with pytest.raises(AppConfigError):
            parse_apps(bad)

    with pytest.raises(SettingsValidationError) as error:
        validate_changes({"AEHUB_APPS": '{"spotify": 3}'})
    assert "AEHUB_APPS" in error.value.errors
    validate_changes({"AEHUB_APPS": '{"spotify": "spotify"}', "AEHUB_INSTANT_COMMANDS": "off"})


# ==============================================================================
# LAUNCH
# ==============================================================================


def _wait_for(path: Path, seconds: float = 10) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def test_an_app_starts_detached(tmp_path, monkeypatch):
    monkeypatch.setattr(apps_module, "in_container", lambda: False)
    marker = tmp_path / "started.txt"
    # The program sleeps a little first: launch() must return before it ends.
    program = f"import time, pathlib; time.sleep(0.3); pathlib.Path({str(marker)!r}).write_text('ok')"

    started = time.perf_counter()
    launch([sys.executable, "-c", program])
    assert time.perf_counter() - started < 0.3
    assert _wait_for(marker)


def test_nothing_starts_in_a_container_or_when_missing(monkeypatch):
    monkeypatch.setattr(apps_module, "in_container", lambda: True)
    with pytest.raises(LaunchError, match="container"):
        launch([sys.executable, "-c", "pass"])

    monkeypatch.setattr(apps_module, "in_container", lambda: False)
    with pytest.raises(LaunchError, match="not found"):
        launch(["/no/such/program-aehub"])


# ==============================================================================
# END TO END: orchestrator -> instant -> Tool Gateway
# ==============================================================================


@pytest.fixture
def instant(agent_infrastructure, tmp_path, monkeypatch):
    """Apps skill (outside a container) and home skill, MQTT recorded, no engine."""
    monkeypatch.setattr(apps_module, "in_container", lambda: False)
    monkeypatch.setattr("app.skills.apps_skill.in_container", lambda: False)
    monkeypatch.delenv("AEHUB_MQTT_URL", raising=False)

    config = tmp_path / "config"
    config.mkdir()
    devices = [
        {"id": "kitchen", "name": "Cucina", "type": "light", "topic": "z2m/kitchen/set"},
        {"id": "front_door", "name": "Porta di casa", "type": "lock", "topic": "z2m/front_door/set"},
    ]
    (config / "home.json").write_text(json.dumps({"devices": devices}), encoding="utf-8")
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(config / "home.json"))

    messages: List[Tuple[str, str]] = []
    mqtt.set_publisher(lambda topic, payload: messages.append((topic, payload)))

    marker = tmp_path / "opened.txt"
    replace_stored({"AEHUB_APPS": json.dumps({"prova": [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ok')"]})})

    registry = agent_infrastructure.use_skills(AppsSkill(), HomeSkill())
    monkeypatch.setattr("app.skills.registry.skill_registry", registry)

    engine = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "From the engine."}]})
    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=SimpleNamespace(ainvoke=engine)))
    monkeypatch.setattr(orchestrator, "speak", AsyncMock(return_value=("", "")))

    yield SimpleNamespace(engine=engine, messages=messages, marker=marker, registry=registry)
    mqtt.set_publisher(None)


def _ask(text: str, channel: str = "text") -> Dict[str, Any]:
    import asyncio

    return asyncio.run(orchestrator.generate_ai_response(text, "", "", OWNER.id, OWNER, input_channel=channel))


def _audit(db_session_factory, tool: str) -> List[Any]:
    with db_session_factory() as db:
        return db.query(AuditLog).filter(AuditLog.tool_name == tool).all()


def test_an_app_opens_without_the_engine(instant, db_session_factory):
    reply = _ask("Apri prova")

    assert reply["transcription"] == "Apro prova."
    assert reply["instant"]["tool"] == "open_app" and reply["instant"]["success"] is True
    assert isinstance(reply["instant"]["ms"], int)
    assert _wait_for(instant.marker)
    instant.engine.assert_not_awaited()
    # Through the Tool Gateway: the call is in the audit, allowed by the policy.
    decisions = [entry.decision for entry in _audit(db_session_factory, "open_app")]
    assert "EXECUTING" in decisions and "ALLOW" in decisions


def test_a_light_answers_in_the_language_spoken(instant, db_session_factory):
    assert _ask("accendi la luce della cucina", channel="voice")["transcription"] == "Cucina: luce accesa."
    assert _ask("turn off the kitchen light")["transcription"] == "Cucina: light off."
    assert _ask("lock the front door")["transcription"] == "Porta di casa: locked."

    assert [topic for topic, _ in instant.messages] == ["z2m/kitchen/set", "z2m/kitchen/set", "z2m/front_door/set"]
    assert [entry.decision for entry in _audit(db_session_factory, "home_set_light")].count("ALLOW") == 2
    instant.engine.assert_not_awaited()


def test_the_engine_takes_everything_else(instant):
    for sentence in ("che tempo fa?", "apri la porta di casa", "apri Word", "apri prova e poi spotify"):
        assert _ask(sentence)["transcription"] == "From the engine."
    assert instant.engine.await_count == 4


def test_turned_off_every_command_goes_to_the_engine(instant):
    replace_stored({"AEHUB_INSTANT_COMMANDS": "off", "AEHUB_APPS": json.dumps({"prova": ["true"]})})

    assert _ask("apri prova")["transcription"] == "From the engine."
    instant.engine.assert_awaited_once()


def test_a_tool_that_is_turned_off_is_refused_and_said(instant, db_session_factory):
    replace_stored({**{"AEHUB_DISABLED_TOOLS": "home_set_light"}})

    reply = _ask("accendi la cucina")

    assert reply["instant"]["success"] is False
    assert reply["transcription"].startswith("Non ci sono riuscita:")
    assert instant.messages == []
    instant.engine.assert_not_awaited()


def test_in_a_container_apps_are_left_to_the_engine(instant, monkeypatch):
    monkeypatch.setattr("app.skills.apps_skill.in_container", lambda: True)
    instant.registry.refresh_skill("apps")

    assert _ask("apri prova")["transcription"] == "From the engine."
    assert not instant.marker.exists()
