"""
@file tests/agent_engine/test_home.py
@description M15 (ADR-021): the MQTT home node.

- the device file: validation, all problems at once, never inside the
  agent's working folder;
- the MQTT message of each action (zigbee2mqtt, tasmota);
- the tools, with a recording publisher; no tools without devices;
- end to end: a light by voice runs, a door unlock waits for approval
  whether typed or spoken, and nothing is published meanwhile;
- the configuration check;
- a real broker (AEHUB_TEST_MQTT_URL, Mosquitto in CI): the message
  arrives on the declared topic.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from app.agent_engine.application import AgentEngine
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.core.settings_service import check_configuration
from app.domain.models.audit import ApprovalRecord
from app.home import mqtt
from app.home.devices import (
    DeviceConfigError,
    UnknownDevice,
    light_message,
    load_devices,
    lock_message,
    parse_devices,
)
from app.skills import home_skill
from app.skills.home_skill import HomeSkill


WORKSPACE_ID = "workspace-home"

DEVICES = {
    "devices": [
        {"id": "living_light", "name": "Luce del soggiorno", "type": "light", "topic": "z2m/living_light/set"},
        {"id": "desk_lamp", "name": "Lampada", "type": "light", "topic": "cmnd/desk_lamp/POWER", "format": "tasmota"},
        {"id": "front_door", "name": "Porta d'ingresso", "type": "lock", "topic": "z2m/front_door/set"},
    ]
}


@pytest.fixture
def published(monkeypatch, tmp_path) -> List[Tuple[str, str]]:
    """
    Devices declared outside the working folder, messages recorded.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "home.json").write_text(json.dumps(DEVICES), encoding="utf-8")
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(workspace))
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(config / "home.json"))

    messages: List[Tuple[str, str]] = []
    mqtt.set_publisher(lambda topic, payload: messages.append((topic, payload)))
    yield messages
    mqtt.set_publisher(None)


# ==============================================================================
# DEVICE FILE
# ==============================================================================


def test_every_problem_is_reported_at_once():
    with pytest.raises(DeviceConfigError) as refused:
        parse_devices(
            {
                "devices": [
                    {"id": "Bad Id", "type": "light", "topic": "a"},
                    {"id": "dup", "type": "light", "topic": "a"},
                    {"id": "dup", "type": "light", "topic": "b"},
                    {"id": "fan", "type": "fan", "topic": "c"},
                    {"id": "spy", "type": "light", "topic": "home/#"},
                    {"id": "door", "type": "lock", "topic": "d", "format": "tasmota"},
                ]
            }
        )

    message = str(refused.value)
    for expected in ("lowercase", "declared twice", "type must be", "no '#'", "lights only"):
        assert expected in message

    with pytest.raises(DeviceConfigError):
        parse_devices({"lights": []})


def test_device_file_inside_the_working_folder_is_refused(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "home.json").write_text(json.dumps(DEVICES), encoding="utf-8")
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(workspace))

    with pytest.raises(DeviceConfigError, match="working folder"):
        load_devices(str(workspace / "home.json"))


def test_no_device_file_means_no_devices(monkeypatch):
    monkeypatch.delenv("AEHUB_HOME_DEVICES", raising=False)

    assert load_devices() == {}
    assert HomeSkill().tools == [] and HomeSkill().get_tool_metadata() == {}


def test_messages():
    devices = parse_devices(DEVICES)

    assert light_message(devices["living_light"], True, 50) == (
        "z2m/living_light/set",
        json.dumps({"state": "ON", "brightness": 127}),
    )
    assert light_message(devices["living_light"], False, 50)[1] == json.dumps({"state": "OFF"})
    assert light_message(devices["desk_lamp"], True) == ("cmnd/desk_lamp/POWER", "ON")
    assert lock_message(devices["front_door"], locked=False)[1] == json.dumps({"state": "UNLOCK"})


# ==============================================================================
# TOOLS
# ==============================================================================


async def test_tools_publish_to_the_declared_topic(published):
    assert "front_door — Porta d'ingresso (lock)" in await home_skill.home_list_devices()

    assert await home_skill.home_set_light("living_light", True, 30) == "Luce del soggiorno: on at 30%."
    assert await home_skill.home_lock("front_door") == "Porta d'ingresso: locked."

    assert published == [
        ("z2m/living_light/set", json.dumps({"state": "ON", "brightness": 76})),
        ("z2m/front_door/set", json.dumps({"state": "LOCK"})),
    ]


async def test_unknown_or_wrong_kind_of_device(published):
    with pytest.raises(UnknownDevice, match="Known locks: front_door"):
        await home_skill.home_unlock("living_light")

    with pytest.raises(UnknownDevice, match="No light named 'garage'"):
        await home_skill.home_set_light("garage", True)

    assert published == []


def test_risk_per_action(published):
    metadata = HomeSkill().get_tool_metadata()

    assert {name: meta.risk_level.value for name, meta in metadata.items()} == {
        "home_list_devices": "low",
        "home_set_light": "low",
        "home_lock": "low",
        "home_unlock": "high",
    }
    assert metadata["home_unlock"].requires_approval is True
    # The model names a device, never a topic or a host.
    for meta in metadata.values():
        assert "topic" not in meta.input_schema["properties"]


def test_broker_url(monkeypatch):
    monkeypatch.delenv("AEHUB_MQTT_URL", raising=False)
    with pytest.raises(mqtt.MqttNotConfigured):
        mqtt.broker()

    monkeypatch.setenv("AEHUB_MQTT_URL", "http://broker")
    with pytest.raises(mqtt.MqttNotConfigured):
        mqtt.broker()

    monkeypatch.setenv("AEHUB_MQTT_URL", "mqtts://broker.lan")
    monkeypatch.setenv("AEHUB_MQTT_USERNAME", "aehub")
    monkeypatch.setenv("AEHUB_MQTT_PASSWORD", "pw")
    settings = mqtt.broker()
    assert settings["port"] == 8883 and settings["tls"] is not None
    assert settings["auth"] == {"username": "aehub", "password": "pw"}


def test_configuration_check(published, monkeypatch, tmp_path):
    monkeypatch.delenv("AEHUB_MQTT_URL", raising=False)
    codes = {issue.code: issue.severity for issue in check_configuration()}
    assert codes["home_broker_missing"] == "error"

    bad = tmp_path / "config" / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(bad))
    codes = {issue.code: issue.severity for issue in check_configuration()}
    assert codes["home_devices_invalid"] == "error"


# ==============================================================================
# END TO END
# ==============================================================================


@pytest.fixture
def home(agent_infrastructure, published):
    agent_infrastructure.use_skills(HomeSkill())
    return published


@pytest.fixture
def admin() -> Principal:
    return Principal(id="owner", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)


def _engine(fake_model, script: List[Any]) -> AgentEngine:
    return AgentEngine(
        model_provider=fake_model.adapter(script),
        checker_provider=fake_model.checker([fake_model.accept(), fake_model.accept()]),
        runtime=AgentRuntime(),
    )


async def test_light_by_voice_runs(home, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "home_set_light", {"device": "living_light", "on": True}),
            fake_model.text("Luce accesa."),
        ],
    )

    await engine.run(session_id="s1", task="Accendi la luce del soggiorno.", principal=admin, input_channel="voice")

    assert home == [("z2m/living_light/set", json.dumps({"state": "ON"}))]


@pytest.mark.parametrize("channel", ["text", "voice"])
async def test_unlocking_a_door_waits_for_approval(home, admin, fake_model, db_session_factory, channel):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "home_unlock", {"device": "front_door"}),
            fake_model.text("Porta aperta."),
        ],
    )

    await engine.run(session_id="s1", task="Apri la porta d'ingresso.", principal=admin, input_channel=channel)

    assert home == []
    with db_session_factory() as db:
        approval = db.query(ApprovalRecord).filter(ApprovalRecord.tool == "home_unlock").one()
        assert approval.decision is None and approval.risk.lower() == "high"


# ==============================================================================
# REAL BROKER
# ==============================================================================


@pytest.mark.skipif(not os.getenv("AEHUB_TEST_MQTT_URL"), reason="no MQTT broker (AEHUB_TEST_MQTT_URL)")
async def test_message_reaches_a_real_broker(tmp_path, monkeypatch):
    from paho.mqtt import client as paho
    from urllib.parse import urlsplit

    url = os.environ["AEHUB_TEST_MQTT_URL"]
    parts = urlsplit(url)
    topic = f"aehub-test/{uuid.uuid4().hex}/set"

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    devices = tmp_path / "home.json"
    devices.write_text(
        json.dumps({"devices": [{"id": "test_light", "type": "light", "topic": topic}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(workspace))
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(devices))
    monkeypatch.setenv("AEHUB_MQTT_URL", url)
    mqtt.set_publisher(None)

    received: "queue.Queue[str]" = queue.Queue()
    subscribed = threading.Event()
    listener = paho.Client(paho.CallbackAPIVersion.VERSION2)
    listener.on_connect = lambda client, *args: client.subscribe(topic, qos=1)
    listener.on_subscribe = lambda *args: subscribed.set()
    listener.on_message = lambda client, userdata, message: received.put(message.payload.decode())
    listener.connect(parts.hostname, parts.port or 1883)
    listener.loop_start()

    try:
        assert subscribed.wait(10), "could not subscribe to the test broker"
        await home_skill.home_set_light("test_light", True)
        assert json.loads(received.get(timeout=10)) == {"state": "ON"}
    finally:
        listener.loop_stop()
        listener.disconnect()


def test_example_device_file_is_valid():
    example = Path(__file__).resolve().parents[2] / "config" / "home.example.json"

    assert set(parse_devices(json.loads(example.read_text(encoding="utf-8")))) == {
        "living_light",
        "desk_lamp",
        "front_door",
    }
