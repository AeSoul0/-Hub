"""
@file tests/agent_engine/test_home_api.py
@description F7 (ADR-028): the home from the Control Plane.

- the broker address and user are runtime settings, validated;
- the state of a device: which topics to ask, how to read the answer;
- devices declared in the Control Plane: validated, audited first, seen by
  the agent's tools, never clashing with the device file;
- a command is the agent's tool through the Tool Gateway: a tool turned off
  stays off, every call is in the audit, and unlocking a door needs the
  user's confirmation, recorded as the approval of that exact call;
- reading a state and checking the broker;
- a real broker (AEHUB_TEST_MQTT_URL, Mosquitto in CI).
"""

from __future__ import annotations

import json
import os
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import home as home_api
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum, resolve_principal
from app.core.settings_service import SettingsValidationError, validate_changes
from app.domain.models.audit import ApprovalRecord, AuditLog
from app.home import mqtt
from app.home.devices import Device, DeviceConfigError, load_devices, parse_state, state_request
from app.home.store import forget
from app.skills import home_skill
from app.skills.home_skill import HomeSkill


WORKSPACE = "workspace-f7"
ADMIN = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id=WORKSPACE)
MEMBER = Principal(id="member", role=RoleEnum.MEMBER, workspace_id=WORKSPACE)

LIGHT = {"id": "living_light", "name": "Luce del soggiorno", "type": "light", "topic": "z2m/living_light/set"}
LAMP = {"id": "desk_lamp", "name": "Lampada", "type": "light", "topic": "cmnd/desk_lamp/POWER", "format": "tasmota"}
DOOR = {"id": "front_door", "name": "Porta d'ingresso", "type": "lock", "topic": "z2m/front_door/set"}


@pytest.fixture(autouse=True)
def clean_settings():
    replace_stored({})
    forget()
    yield
    replace_stored({})
    forget()


@pytest.fixture
def home(agent_infrastructure, tmp_path, monkeypatch):
    """
    No device yet, the home skill in the registry, messages recorded.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(workspace))
    monkeypatch.delenv("AEHUB_HOME_DEVICES", raising=False)
    monkeypatch.delenv("AEHUB_MQTT_URL", raising=False)
    monkeypatch.delenv("AEHUB_MQTT_USERNAME", raising=False)
    monkeypatch.delenv("AEHUB_MQTT_PASSWORD", raising=False)

    messages: List[Tuple[str, str]] = []
    mqtt.set_publisher(lambda topic, payload: messages.append((topic, payload)))

    registry = agent_infrastructure.use_skills(HomeSkill())
    monkeypatch.setattr("app.skills.registry.skill_registry", registry)

    yield SimpleNamespace(messages=messages, registry=registry)
    mqtt.set_publisher(None)


def _client(principal: Principal = ADMIN) -> TestClient:
    app = FastAPI()
    app.include_router(home_api.router)
    app.dependency_overrides[resolve_principal] = lambda: principal
    return TestClient(app)


def _declare(*devices: Dict[str, Any]) -> TestClient:
    client = _client()
    response = client.put("/api/home/devices", json={"devices": list(devices)})
    assert response.status_code == 200, response.text
    return client


def _device_file(tmp_path, monkeypatch, *devices: Dict[str, Any]) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "home.json").write_text(json.dumps({"devices": list(devices)}), encoding="utf-8")
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(config / "home.json"))


def _audit(db_session_factory, tool: str) -> List[Any]:
    with db_session_factory() as db:
        return db.query(AuditLog).filter(AuditLog.tool_name == tool).all()


# ==============================================================================
# BROKER SETTINGS
# ==============================================================================


def test_broker_settings_apply_without_restart(monkeypatch):
    monkeypatch.delenv("AEHUB_MQTT_URL", raising=False)
    monkeypatch.delenv("AEHUB_MQTT_USERNAME", raising=False)
    monkeypatch.setenv("AEHUB_MQTT_PASSWORD", "pw")

    with pytest.raises(mqtt.MqttNotConfigured):
        mqtt.broker()

    replace_stored({"AEHUB_MQTT_URL": "mqtt://192.168.1.10:1884", "AEHUB_MQTT_USERNAME": "aehub"})
    settings = mqtt.broker()

    assert settings["hostname"] == "192.168.1.10" and settings["port"] == 1884
    assert settings["auth"] == {"username": "aehub", "password": "pw"}


def test_an_impossible_port_is_not_a_broker():
    replace_stored({"AEHUB_MQTT_URL": "mqtt://broker.lan:99999"})

    with pytest.raises(mqtt.MqttNotConfigured):
        mqtt.broker()


@pytest.mark.parametrize(
    "name, value",
    [
        ("AEHUB_MQTT_URL", "http://broker.lan"),
        ("AEHUB_MQTT_URL", "mqtt://user:secret@broker.lan"),
        ("AEHUB_MQTT_URL", "mqtt://broker.lan/topic"),
        ("AEHUB_MQTT_USERNAME", "two words"),
    ],
)
def test_broker_settings_are_validated(name, value):
    with pytest.raises(SettingsValidationError) as caught:
        validate_changes({name: value})

    assert name in caught.value.errors


# ==============================================================================
# STATE OF A DEVICE
# ==============================================================================


def test_how_a_state_is_asked():
    light = Device(id="a", name="a", type="light", topic="z2m/a/set")
    lamp = Device(id="b", name="b", type="light", topic="cmnd/b/POWER", format="tasmota")

    assert state_request(light) == ("z2m/a", "z2m/a/get", json.dumps({"state": ""}))
    assert state_request(lamp) == ("stat/b/POWER", "cmnd/b/POWER", "")
    assert state_request(Device(id="c", name="c", type="light", topic="custom/c")) is None
    assert state_request(Device(id="d", name="d", type="light", topic="other/d", format="tasmota")) is None


def test_how_an_answer_is_read():
    light = Device(id="a", name="a", type="light", topic="z2m/a/set")
    lamp = Device(id="b", name="b", type="light", topic="cmnd/b/POWER", format="tasmota")
    door = Device(id="c", name="c", type="lock", topic="z2m/c/set")

    assert parse_state(light, '{"state": "ON", "brightness": 127}') == {"state": "on", "brightness": 50}
    assert parse_state(lamp, "OFF\n") == {"state": "off"}
    assert parse_state(door, '{"state": "LOCK"}') == {"state": "locked"}
    assert parse_state(door, '{"state": "UNLOCK"}') == {"state": "unlocked"}

    # A device answers what it likes: nothing odd becomes a state.
    assert parse_state(light, "not json") == {"state": None}
    assert parse_state(light, "[1, 2]") == {"state": None}
    assert parse_state(door, '{"state": "ON"}') == {"state": None}
    assert parse_state(light, '{"state": "LOCK"}') == {"state": None}


# ==============================================================================
# DEVICES
# ==============================================================================


def test_devices_from_the_control_plane_reach_the_agent(home, db_session_factory):
    assert home.registry.get_tool_metadata("home_set_light") is None

    client = _declare(LIGHT, DOOR)

    assert sorted(load_devices()) == ["front_door", "living_light"]
    assert home.registry.get_tool_metadata("home_set_light") is not None
    assert home.registry.get_tool_metadata("home_unlock").risk_level.value.upper() == "HIGH"

    view = client.get("/api/home").json()
    assert [(d["id"], d["source"]) for d in view["devices"]] == [("front_door", "app"), ("living_light", "app")]
    assert view["tools"]["home_unlock"] == {"registered": True, "disabled": False}

    entries = _audit(db_session_factory, "home.devices.update")
    assert len(entries) == 1 and "z2m/living_light/set" in entries[0].execution_result

    _declare()

    assert load_devices() == {}
    assert home.registry.get_tool_metadata("home_set_light") is None


def test_every_problem_of_a_list_is_reported_and_nothing_changes(home, db_session_factory):
    client = _client()
    response = client.put(
        "/api/home/devices",
        json={
            "devices": [
                {"id": "Bad Id", "type": "light", "topic": "a"},
                {"id": "spy", "type": "light", "topic": "home/#"},
                {"id": "fan", "type": "fan", "topic": "c"},
            ]
        },
    )

    assert response.status_code == 422
    for word in ("id must be", "topic must be", "type must be"):
        assert word in response.json()["detail"]

    assert load_devices() == {}
    assert _audit(db_session_factory, "home.devices.update") == []


def test_an_id_lives_in_one_place_only(home, tmp_path, monkeypatch, db_session_factory):
    _device_file(tmp_path, monkeypatch, LAMP)

    client = _client()
    refused = client.put("/api/home/devices", json={"devices": [LAMP]})
    assert refused.status_code == 422 and "Already in the device file" in refused.json()["detail"]

    _declare(LIGHT)

    view = client.get("/api/home").json()
    assert [(d["id"], d["source"]) for d in view["devices"]] == [("living_light", "app"), ("desk_lamp", "file")]
    assert view["file"].endswith("home.json")

    # The same id added to the file afterwards turns the devices off, and
    # says why, instead of silently picking one.
    (tmp_path / "config" / "home.json").write_text(json.dumps({"devices": [LAMP, LIGHT]}), encoding="utf-8")

    with pytest.raises(DeviceConfigError):
        load_devices()

    view = client.get("/api/home").json()
    assert "living_light" in view["errors"]["all"]


def test_a_wrong_device_file_keeps_the_page_working(home, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "home.json").write_text("not json", encoding="utf-8")
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(config / "home.json"))

    view = _client().get("/api/home").json()

    assert view["devices"] == [] and "not valid JSON" in view["errors"]["file"]


# ==============================================================================
# COMMANDS
# ==============================================================================


def test_a_command_is_the_tool_through_the_gateway(home, db_session_factory):
    client = _declare(LIGHT, LAMP)

    response = client.post(
        "/api/home/devices/living_light/command",
        json={"action": "on", "brightness": 50},
    )

    assert response.status_code == 200, response.text
    assert home.messages == [("z2m/living_light/set", json.dumps({"state": "ON", "brightness": 127}))]

    device = response.json()["device"]
    assert device["command"]["state"] == "on"
    assert device["command"]["brightness"] == 50
    assert device["command"]["by"] == "control-plane"

    decisions = [entry.decision for entry in _audit(db_session_factory, "home_set_light")]
    assert "EXECUTING" in decisions and "ALLOW" in decisions

    client.post("/api/home/devices/desk_lamp/command", json={"action": "off"})
    assert home.messages[-1] == ("cmnd/desk_lamp/POWER", "OFF")


def test_a_tool_turned_off_stays_off(home, db_session_factory):
    client = _declare(LIGHT)
    replace_stored({"AEHUB_DISABLED_TOOLS": "home_set_light"})

    response = client.post("/api/home/devices/living_light/command", json={"action": "on"})

    assert response.status_code == 403
    assert home.messages == []
    assert client.get("/api/home").json()["tools"]["home_set_light"]["disabled"] is True
    assert [entry.decision for entry in _audit(db_session_factory, "home_set_light")] == ["DENY"]


def test_unlocking_needs_the_confirmation(home, db_session_factory):
    client = _declare(DOOR)

    response = client.post("/api/home/devices/front_door/command", json={"action": "unlock"})

    assert response.status_code == 428
    assert home.messages == []
    with db_session_factory() as db:
        assert db.query(ApprovalRecord).count() == 0


def test_the_confirmation_is_the_approval_of_that_call(home, db_session_factory):
    client = _declare(DOOR)

    response = client.post(
        "/api/home/devices/front_door/command",
        json={"action": "unlock", "confirm": True},
    )

    assert response.status_code == 200, response.text
    assert home.messages == [("z2m/front_door/set", json.dumps({"state": "UNLOCK"}))]

    with db_session_factory() as db:
        approval = db.query(ApprovalRecord).filter(ApprovalRecord.tool == "home_unlock").one()
        assert approval.decision == "ALLOW"
        assert approval.decided_by == approval.requested_by == ADMIN.id
        assert approval.risk.lower() == "high"

    # Nothing is left waiting in the Approvals page.
    with db_session_factory() as db:
        assert db.query(ApprovalRecord).filter(ApprovalRecord.decision.is_(None)).count() == 0

    assert "ALLOW" in [entry.decision for entry in _audit(db_session_factory, "home_unlock")]


def test_locking_needs_no_confirmation(home):
    client = _declare(DOOR)

    response = client.post("/api/home/devices/front_door/command", json={"action": "lock"})

    assert response.status_code == 200
    assert home.messages == [("z2m/front_door/set", json.dumps({"state": "LOCK"}))]


@pytest.mark.parametrize(
    "device, body, status",
    [
        ("nobody", {"action": "on"}, 404),
        ("front_door", {"action": "on"}, 422),
        ("living_light", {"action": "unlock", "confirm": True}, 422),
        ("living_light", {"action": "explode"}, 422),
        ("living_light", {"action": "on", "brightness": 101}, 422),
    ],
)
def test_wrong_commands_never_reach_the_broker(home, device, body, status):
    client = _declare(LIGHT, DOOR)

    assert client.post(f"/api/home/devices/{device}/command", json=body).status_code == status
    assert home.messages == []


def test_a_broker_failure_is_reported_and_not_remembered(home):
    client = _declare(LIGHT)

    def down(topic: str, payload: str) -> None:
        raise ConnectionRefusedError("broker down")

    mqtt.set_publisher(down)

    response = client.post("/api/home/devices/living_light/command", json={"action": "on"})

    assert response.status_code == 502 and "broker down" in response.json()["detail"]
    assert "command" not in client.get("/api/home").json()["devices"][0]


async def test_a_command_of_the_agent_shows_too(home):
    _declare(LIGHT)

    await home_skill.home_set_light("living_light", True, 30)

    device = _client().get("/api/home").json()["devices"][0]
    assert device["command"]["state"] == "on"
    assert device["command"]["brightness"] == 30
    assert device["command"]["by"] == "agent"


# ==============================================================================
# STATE AND BROKER CHECK
# ==============================================================================


def test_reading_a_state(home, monkeypatch):
    client = _declare(LIGHT)
    asked: List[Tuple[str, str, str]] = []

    def answer(watch: str, ask: str, payload: str) -> str:
        asked.append((watch, ask, payload))
        return '{"state": "OFF"}'

    monkeypatch.setattr(mqtt, "request_state", answer)

    response = client.post("/api/home/devices/living_light/state")

    assert response.status_code == 200, response.text
    assert asked == [("z2m/living_light", "z2m/living_light/get", '{"state": ""}')]
    assert response.json()["device"]["reading"]["state"] == "off"

    # Asking is not a command.
    assert home.messages == []


def test_reading_a_state_can_fail(home, monkeypatch):
    client = _declare(LIGHT, {"id": "odd", "type": "light", "topic": "custom/odd"})

    monkeypatch.setattr(mqtt, "request_state", lambda *args: None)
    assert client.post("/api/home/devices/living_light/state").status_code == 504

    assert client.post("/api/home/devices/odd/state").status_code == 422
    assert client.post("/api/home/devices/nobody/state").status_code == 404

    def missing(*args: Any) -> None:
        raise mqtt.MqttNotConfigured("No MQTT broker.")

    monkeypatch.setattr(mqtt, "request_state", missing)
    assert client.post("/api/home/devices/living_light/state").status_code == 503

    def refused(*args: Any) -> None:
        raise mqtt.MqttError("The broker refused the connection.")

    monkeypatch.setattr(mqtt, "request_state", refused)
    assert client.post("/api/home/devices/living_light/state").status_code == 502


def test_checking_the_broker(home, monkeypatch):
    client = _client()

    outcome = client.post("/api/home/broker/check").json()
    assert outcome["ok"] is False and "No MQTT broker" in outcome["error"]

    monkeypatch.setattr(mqtt, "check_broker", lambda: None)
    assert client.post("/api/home/broker/check").json() == {"ok": True, "error": None}


def test_the_password_is_never_shown(home, monkeypatch):
    monkeypatch.setenv("AEHUB_MQTT_PASSWORD", "s3cret-value")
    replace_stored({"AEHUB_MQTT_URL": "mqtt://broker.lan", "AEHUB_MQTT_USERNAME": "aehub"})

    response = _client().get("/api/home")

    assert response.json()["broker"] == {
        "url": "mqtt://broker.lan",
        "username": "aehub",
        "password_set": True,
        "error": None,
    }
    assert "s3cret-value" not in response.text


# ==============================================================================
# PERMISSIONS
# ==============================================================================


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("put", "/api/home/devices", {"devices": []}),
        ("post", "/api/home/devices/living_light/command", {"action": "on"}),
        ("post", "/api/home/devices/living_light/state", None),
        ("post", "/api/home/broker/check", None),
    ],
)
def test_only_an_admin_controls_the_home(home, method, path, body):
    _declare(LIGHT)

    client = _client(MEMBER)
    response = getattr(client, method)(path, **({"json": body} if body is not None else {}))

    assert response.status_code == 403
    assert home.messages == []


# ==============================================================================
# REAL BROKER
# ==============================================================================


@pytest.mark.skipif(not os.getenv("AEHUB_TEST_MQTT_URL"), reason="no MQTT broker (AEHUB_TEST_MQTT_URL)")
def test_a_real_broker_answers(monkeypatch):
    from paho.mqtt import publish

    url = os.environ["AEHUB_TEST_MQTT_URL"]
    parts = urlsplit(url)
    topic = f"aehub-test/{uuid.uuid4().hex}"

    monkeypatch.setenv("AEHUB_MQTT_URL", url)
    monkeypatch.delenv("AEHUB_MQTT_USERNAME", raising=False)

    mqtt.check_broker()

    # The state a device keeps retained on its topic counts as the answer.
    publish.single(topic, '{"state": "ON"}', qos=1, retain=True, hostname=parts.hostname, port=parts.port or 1883)
    try:
        assert mqtt.request_state(topic, f"{topic}/get", '{"state": ""}') == '{"state": "ON"}'
        assert mqtt.request_state(f"{topic}/silent", f"{topic}/silent/get", "", timeout=0.5) is None
    finally:
        publish.single(topic, "", qos=1, retain=True, hostname=parts.hostname, port=parts.port or 1883)


def test_an_unreachable_broker_is_an_error(monkeypatch):
    # A closed port on this machine refuses at once.
    replace_stored({"AEHUB_MQTT_URL": "mqtt://127.0.0.1:1"})

    with pytest.raises(mqtt.MqttError):
        mqtt.check_broker(timeout=1)
