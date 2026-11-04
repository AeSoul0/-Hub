"""
@file backend/app/home/store.py
@description Home devices declared in the Control Plane, and what ÆHub last
did with each device (F7, ADR-028).

The devices live in one private row of `app_settings` ("_home_devices"), as
the same {"devices": [...]} document as the device file: the database is out
of reach of the agent's tools, so the agent cannot declare a device on a
topic of its choice. A change is written to the audit chain before it
applies, then the home tools are re-read.

The last command and the last state read of each device are kept in memory
only: they say what ÆHub did since it started, not the device's history.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.home.devices import MAX_DEVICES, Device, DeviceConfigError, file_devices, parse_devices


logger = logging.getLogger(__name__)

STORE_KEY = "_home_devices"


def stored_devices() -> Dict[str, Device]:
    """
    The devices declared in the Control Plane; none when the database cannot
    be read (the agent then sees only the device file's).
    """
    from app.core.db import SessionLocal
    from app.domain.models.settings import AppSetting

    try:
        with SessionLocal() as db:
            row = db.get(AppSetting, STORE_KEY)
            raw = row.value if row is not None else None
    except Exception as exc:
        logger.warning("Home devices of the Control Plane not readable: %s", exc)
        return {}

    if not raw:
        return {}

    try:
        return parse_devices(json.loads(raw), source="app")
    except (ValueError, DeviceConfigError) as exc:
        logger.error("Home devices of the Control Plane are invalid: %s", exc)
        raise DeviceConfigError(f"Devices of the Control Plane: {exc}") from exc


def check_devices(entries: List[Dict[str, Any]]) -> Dict[str, Device]:
    """
    Validate a new list for the Control Plane: the device file's rules, no
    id already in the device file, at most MAX_DEVICES in all.
    """
    devices = parse_devices({"devices": entries}, source="app")

    try:
        declared = file_devices()
    except DeviceConfigError:
        declared = {}

    clash = sorted(set(devices) & set(declared))
    if clash:
        raise DeviceConfigError(f"Already in the device file: {', '.join(clash)}.")

    if len(devices) + len(declared) > MAX_DEVICES:
        raise DeviceConfigError(f"At most {MAX_DEVICES} devices.")

    return devices


def save_devices(db: Any, entries: List[Dict[str, Any]], principal_id: str, workspace_id: str) -> Dict[str, Device]:
    """
    Replace the devices of the Control Plane. Raises DeviceConfigError with
    every problem; audited as `home.devices.update` before the change.
    """
    from app.domain.models.settings import AppSetting
    from app.runtime.audit_chain import append_audit_record

    devices = check_devices(entries)
    document = {
        "devices": [
            {key: value for key, value in device.to_dict().items() if key != "source"}
            for device in devices.values()
        ]
    }

    append_audit_record(
        db,
        session_id="control-plane",
        principal_id=principal_id,
        workspace_id=workspace_id,
        tool_name="home.devices.update",
        risk="high",
        decision="ALLOW",
        success=True,
        execution_result=json.dumps(document, sort_keys=True, ensure_ascii=False),
    )

    row = db.get(AppSetting, STORE_KEY)

    if not devices:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(AppSetting(key=STORE_KEY, value=json.dumps(document), updated_by=principal_id))
    else:
        row.value = json.dumps(document)
        row.updated_by = principal_id

    db.commit()

    for device_id in set(_activity) - set(devices) - set(_safe_file_ids()):
        forget(device_id)

    refresh_home_tools()
    return devices


def _safe_file_ids() -> List[str]:
    try:
        return list(file_devices())
    except DeviceConfigError:
        return []


def refresh_home_tools() -> None:
    """
    Re-read the home tools: they exist only while some device is declared.
    """
    from app.skills.registry import skill_registry

    if skill_registry.get_skill("home") is not None:
        skill_registry.refresh_skill("home")


# ==============================================================================
# WHAT ÆHUB LAST DID
# ==============================================================================

_activity: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_command(device_id: str, state: str, brightness: Optional[int] = None, by: str = "agent") -> None:
    entry: Dict[str, Any] = {"state": state, "at": _now(), "by": by}
    if brightness is not None:
        entry["brightness"] = brightness
    with _lock:
        current = dict(_activity.get(device_id, {}))
        current["command"] = entry
        _activity[device_id] = current


def record_reading(device_id: str, reading: Dict[str, Any]) -> None:
    with _lock:
        current = dict(_activity.get(device_id, {}))
        current["reading"] = {**reading, "at": _now()}
        _activity[device_id] = current


def activity(device_id: str) -> Dict[str, Any]:
    with _lock:
        return dict(_activity.get(device_id, {}))


def forget(device_id: Optional[str] = None) -> None:
    with _lock:
        if device_id is None:
            _activity.clear()
        else:
            _activity.pop(device_id, None)


__all__ = [
    "STORE_KEY",
    "activity",
    "check_devices",
    "forget",
    "record_command",
    "record_reading",
    "refresh_home_tools",
    "save_devices",
    "stored_devices",
]
