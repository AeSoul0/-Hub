"""
@file backend/app/home/devices.py
@description The declared home devices and the MQTT message for each action.

AEHUB_HOME_DEVICES points to a JSON file written by the user:

    {
      "devices": [
        {"id": "living_light", "name": "Luce del soggiorno", "type": "light",
         "topic": "zigbee2mqtt/living_light/set"},
        {"id": "front_door", "name": "Porta d'ingresso", "type": "lock",
         "topic": "zigbee2mqtt/front_door/set"},
        {"id": "desk_lamp", "name": "Lampada", "type": "light",
         "topic": "cmnd/desk_lamp/POWER", "format": "tasmota"}
      ]
    }

Formats: "zigbee2mqtt" (default; JSON {"state": ...}) and "tasmota" (plain
ON/OFF on cmnd/<device>/POWER, lights only). The agent never sees or sets a
topic: it names a declared device id, and this module builds the message.

The file must live outside the agent's working folders (AEHUB_ALLOWED_DIRS):
there the agent's file tools could rewrite it and declare a "device" on any
topic.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DEVICE_TYPES = ("light", "lock")
FORMATS = ("zigbee2mqtt", "tasmota")
MAX_DEVICES = 200

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TOPIC = re.compile(r"^[^#+\x00]{1,256}$")


class DeviceConfigError(ValueError):
    pass


class UnknownDevice(ValueError):
    pass


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    type: str
    topic: str
    format: str = "zigbee2mqtt"


def parse_devices(raw: object) -> Dict[str, Device]:
    """
    Validate a device file's content; every problem is reported at once.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("devices"), list):
        raise DeviceConfigError('The device file must be {"devices": [...]}.')

    entries = raw["devices"]
    if len(entries) > MAX_DEVICES:
        raise DeviceConfigError(f"At most {MAX_DEVICES} devices.")

    devices: Dict[str, Device] = {}
    errors: List[str] = []

    for index, entry in enumerate(entries):
        where = f"device {index + 1}"

        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object.")
            continue

        device_id = entry.get("id")
        device_type = entry.get("type")
        topic = entry.get("topic")
        fmt = entry.get("format", "zigbee2mqtt")
        name = entry.get("name") or device_id

        if not isinstance(device_id, str) or not _ID.match(device_id):
            errors.append(f"{where}: id must be lowercase letters, digits, '_' or '-'.")
            continue
        where = f"device '{device_id}'"

        if device_id in devices:
            errors.append(f"{where}: declared twice.")
        if device_type not in DEVICE_TYPES:
            errors.append(f"{where}: type must be one of {', '.join(DEVICE_TYPES)}.")
        if not isinstance(topic, str) or not _TOPIC.match(topic):
            errors.append(f"{where}: topic must be a plain MQTT topic (no '#' or '+').")
        if fmt not in FORMATS:
            errors.append(f"{where}: format must be one of {', '.join(FORMATS)}.")
        if fmt == "tasmota" and device_type == "lock":
            errors.append(f"{where}: the tasmota format controls lights only.")
        if not isinstance(name, str) or len(name) > 100:
            errors.append(f"{where}: name must be text of at most 100 characters.")

        devices[device_id] = Device(
            id=device_id,
            name=str(name),
            type=str(device_type),
            topic=str(topic),
            format=str(fmt),
        )

    if errors:
        raise DeviceConfigError(" ".join(errors))

    return devices


def load_devices(path: Optional[str] = None) -> Dict[str, Device]:
    """
    The devices of AEHUB_HOME_DEVICES; none when it is not set.
    """
    location = path if path is not None else os.getenv("AEHUB_HOME_DEVICES", "").strip()

    if not location:
        return {}

    file = Path(location).expanduser()

    from app.agent_engine.guardrails import allowed_directories

    resolved = Path(os.path.realpath(file))
    for root in allowed_directories():
        if resolved == root or root in resolved.parents:
            raise DeviceConfigError(
                f"Device file {file} is inside the agent's working folder {root}: move it out, "
                "where the agent's file tools cannot change it."
            )

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeviceConfigError(f"Device file {file} not found.") from exc
    except json.JSONDecodeError as exc:
        raise DeviceConfigError(f"Device file {file} is not valid JSON: {exc}") from exc

    return parse_devices(raw)


def find(devices: Dict[str, Device], device_id: str, device_type: str) -> Device:
    device = devices.get(device_id)

    if device is None or device.type != device_type:
        known = ", ".join(sorted(d.id for d in devices.values() if d.type == device_type)) or "none"
        raise UnknownDevice(f"No {device_type} named '{device_id}'. Known {device_type}s: {known}.")

    return device


def light_message(device: Device, on: bool, brightness: Optional[int] = None) -> Tuple[str, str]:
    if device.format == "tasmota":
        return device.topic, "ON" if on else "OFF"

    payload: Dict[str, object] = {"state": "ON" if on else "OFF"}

    if on and brightness is not None:
        # zigbee2mqtt brightness is 0-254; the agent speaks in percent.
        payload["brightness"] = round(max(0, min(100, brightness)) * 254 / 100)

    return device.topic, json.dumps(payload)


def lock_message(device: Device, locked: bool) -> Tuple[str, str]:
    return device.topic, json.dumps({"state": "LOCK" if locked else "UNLOCK"})


__all__ = [
    "Device",
    "DeviceConfigError",
    "UnknownDevice",
    "find",
    "light_message",
    "load_devices",
    "lock_message",
    "parse_devices",
]
