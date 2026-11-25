"""
@file backend/app/api/home.py
@description Home devices from the Control Plane (F7, ADR-028).

GET  /api/home                        the devices (device file and Control
                                      Plane), what ÆHub last did with each,
                                      the broker settings and their problems.
PUT  /api/home/devices                the devices declared in the Control
                                      Plane (admin); audited first.
POST /api/home/devices/{id}/command   on / off / lock / unlock (admin).
POST /api/home/devices/{id}/state     ask the device its state (admin).
POST /api/home/broker/check           connect to the broker once (admin).

A command is the agent's own home tool, run through the Tool Gateway: the
same policy (a tool turned off in STRUMENTI stays off), schema, guardrails
and audit chain as a call from a run. Unlocking a door is HIGH: the page asks
the user to confirm, and the confirmation is recorded as the approval of
that exact call, decided by the user who clicked.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, resolve_principal
from app.domain.models.identity import RoleEnum
from app.home import mqtt
from app.home.devices import (
    DEVICE_TYPES,
    FORMATS,
    MAX_DEVICES,
    DeviceConfigError,
    device_file,
    file_devices,
    load_devices,
    parse_state,
    state_request,
)
from app.home.store import activity, record_command, record_reading, save_devices, stored_devices


router = APIRouter(
    prefix="/api/home",
    tags=["home"],
)

HOME_TOOLS = ("home_list_devices", "home_set_light", "home_lock", "home_unlock")
SESSION_ID = "control-plane"

# Action -> (device type, tool).
ACTIONS = {
    "on": ("light", "home_set_light"),
    "off": ("light", "home_set_light"),
    "lock": ("lock", "home_lock"),
    "unlock": ("lock", "home_unlock"),
}


class DeviceIn(BaseModel):
    id: str = Field(max_length=64)
    name: Optional[str] = Field(default=None, max_length=100)
    type: str = Field(max_length=16)
    topic: str = Field(max_length=256)
    format: str = Field(default="zigbee2mqtt", max_length=16)


class DevicesIn(BaseModel):
    devices: List[DeviceIn] = Field(max_length=MAX_DEVICES)


class Command(BaseModel):
    action: Literal["on", "off", "lock", "unlock"]
    brightness: Optional[int] = Field(default=None, ge=0, le=100)
    # Required for a HIGH action: the user confirmed it on screen.
    confirm: bool = False


def _require_admin(principal: Principal) -> None:
    if principal.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only an admin can control the home.")


def _device(device_id: str):
    try:
        devices = load_devices()
    except DeviceConfigError as exc:
        raise HTTPException(status_code=409, detail=f"Home devices are off: {exc}") from exc

    device = devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Unknown device.")
    return device


def _view() -> Dict[str, Any]:
    from app.core.runtime_config import config_value
    from app.core.security import disabled_tools
    from app.desktop.launch import desktop_mode
    from app.skills.registry import skill_registry

    devices: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}

    for source, load in (("file", file_devices), ("app", stored_devices)):
        try:
            loaded = load()
        except DeviceConfigError as exc:
            errors[source] = str(exc)
            continue
        devices.extend({**device.to_dict(), **activity(device.id)} for device in loaded.values())

    try:
        load_devices()
    except DeviceConfigError as exc:
        errors.setdefault("all", str(exc))

    try:
        mqtt.broker()
        broker_error = None
    except mqtt.MqttNotConfigured as exc:
        broker_error = str(exc)

    off = disabled_tools()

    return {
        "devices": sorted(devices, key=lambda d: (d["source"], d["id"])),
        "errors": errors,
        "file": device_file() or None,
        "broker": {
            "url": config_value("AEHUB_MQTT_URL", "") or "",
            "username": config_value("AEHUB_MQTT_USERNAME", "") or "",
            "password_set": bool(os.getenv("AEHUB_MQTT_PASSWORD")),
            "error": broker_error,
        },
        "tools": {
            name: {
                "registered": skill_registry.get_tool_metadata(name) is not None,
                "disabled": name in off,
            }
            for name in HOME_TOOLS
        },
        "desktop": desktop_mode(),
        "limits": {"max_devices": MAX_DEVICES, "types": list(DEVICE_TYPES), "formats": list(FORMATS)},
    }


@router.get("")
async def home_status(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    del principal
    return _view()


@router.put("/devices")
async def update_devices(
    body: DevicesIn,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.core.db import SessionLocal

    _require_admin(principal)

    entries = [device.model_dump(exclude_none=True) for device in body.devices]

    try:
        with SessionLocal() as db:
            save_devices(db, entries, principal.id, principal.workspace_id)
    except DeviceConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _view()


@router.post("/devices/{device_id}/command")
async def command(
    device_id: str,
    body: Command,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    from app.agent_engine.approval.manager import ApprovalManager
    from app.agent_engine.errors import ApprovalRequiredError
    from app.agent_engine.runtime import AgentRuntime
    from app.core.security import TaskExecutionContext
    from app.runtime.tool_gateway import ToolGateway, ToolInvocation

    _require_admin(principal)

    device = _device(device_id)
    device_type, tool_name = ACTIONS[body.action]

    if device.type != device_type:
        raise HTTPException(status_code=422, detail=f"'{body.action}' is not an action of a {device.type}.")

    arguments: Dict[str, Any] = {"device": device.id}
    if tool_name == "home_set_light":
        arguments["on"] = body.action == "on"
        if body.action == "on" and body.brightness is not None:
            arguments["brightness"] = body.brightness

    try:
        tool, _ = AgentRuntime._resolve_tool(tool_name)
        spec = AgentRuntime._build_tool_spec(tool_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"The home tools are not available: {exc}") from exc

    needs_approval = spec.requires_approval or spec.risk_level in ("HIGH", "CRITICAL")

    if needs_approval and not body.confirm:
        raise HTTPException(status_code=428, detail="This action needs your confirmation.")

    run_id = f"home-{uuid.uuid4().hex}"
    context = TaskExecutionContext(workspace_id=principal.workspace_id)

    async def executor(**call: Any) -> Any:
        return await AgentRuntime._execute_registered_tool(
            tool=tool,
            arguments=call,
            session_id=SESSION_ID,
            workspace_id=principal.workspace_id,
            principal_id=principal.id,
        )

    def invocation() -> ToolInvocation:
        return ToolInvocation(
            tool_name=tool_name,
            arguments=dict(arguments),
            principal=principal,
            session_id=SESSION_ID,
            spec=spec,
            tool_call_id=f"call-{body.action}",
            run_id=run_id,
        )

    try:
        result = await ToolGateway.execute(invocation(), executor, task_context=context)
    except ApprovalRequiredError as exc:
        if not exc.approval_id:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # The policy asked for approval: the user's confirmation is it; with
        # no confirmation the request is closed at once, never left pending.
        decision = "ALLOW" if body.confirm else "DENY"
        await ApprovalManager.grant_approval(
            req_id=exc.approval_id,
            decision=decision,
            decided_by=principal.id,
            workspace_id=principal.workspace_id,
        )

        if decision == "DENY":
            raise HTTPException(status_code=428, detail="This action needs your confirmation.") from exc

        result = await ToolGateway.execute(invocation(), executor, task_context=context)

    if not result.success:
        error = result.error or "The command failed."
        status = 403 if error.startswith("Unauthorized") else 502
        raise HTTPException(status_code=status, detail=error)

    state = {"on": "on", "off": "off", "lock": "locked", "unlock": "unlocked"}[body.action]
    record_command(device.id, state, arguments.get("brightness"), by="control-plane")

    return {
        "device": {**device.to_dict(), **activity(device.id)},
        "output": result.output,
        "audit_id": result.audit_id,
    }


@router.post("/devices/{device_id}/state")
async def read_state(
    device_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    _require_admin(principal)

    device = _device(device_id)
    request = state_request(device)

    if request is None:
        raise HTTPException(
            status_code=422,
            detail="This device's topic has no known shape: its state cannot be asked.",
        )

    try:
        answer = await asyncio.to_thread(mqtt.request_state, *request)
    except mqtt.MqttNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except mqtt.MqttError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if answer is None:
        raise HTTPException(status_code=504, detail="The device did not answer.")

    reading = parse_state(device, answer)
    record_reading(device.id, reading)

    return {"device": {**device.to_dict(), **activity(device.id)}}


@router.post("/broker/check")
async def check_broker(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    _require_admin(principal)

    try:
        await asyncio.to_thread(mqtt.check_broker)
    except (mqtt.MqttNotConfigured, mqtt.MqttError) as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "error": None}
