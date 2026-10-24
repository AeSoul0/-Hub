"""
@file backend/app/skills/home_skill.py
@description Home devices over MQTT (roadmap M15, ADR-021).

One tool per action, so each carries its own risk:

    home_list_devices   LOW    the declared devices
    home_set_light      LOW    a light on or off, optional brightness
    home_lock           LOW    lock a door (makes the home safer)
    home_unlock         HIGH   unlock a door: always needs approval

The agent names a device id from the user's device file; the topic and the
message are built here, so the model can reach no other topic or host.
Without a device file (AEHUB_HOME_DEVICES) the skill offers no tools.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from app.home.devices import (
    DeviceConfigError,
    find,
    light_message,
    load_devices,
    lock_message,
)
from app.home.mqtt import PUBLISH_TIMEOUT_SECONDS, publish

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


logger = logging.getLogger(__name__)

_DEVICE_ID = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"}

# Words that pick these tools in the skill index (M15), Italian and English.
EXAMPLES = {
    "home_list_devices": ["dispositivi", "casa", "quali luci", "devices", "home", "which lights"],
    "home_set_light": ["accendi", "spegni", "luce", "luci", "lampada", "turn on", "turn off", "light", "lights", "lamp", "brightness"],
    "home_lock": ["chiudi a chiave", "blocca la porta", "serratura", "lock the door", "lock"],
    "home_unlock": ["apri la porta", "sblocca", "serratura", "unlock", "open the door"],
}


async def _send(topic: str, payload: str) -> None:
    await asyncio.wait_for(
        asyncio.to_thread(publish, topic, payload),
        timeout=PUBLISH_TIMEOUT_SECONDS + 5,
    )


async def home_list_devices() -> str:
    """
    List the home devices the user declared.
    """
    devices = load_devices()

    if not devices:
        return "No home device is declared."

    return "\n".join(
        f"{device.id} — {device.name} ({device.type})"
        for device in sorted(devices.values(), key=lambda d: d.id)
    )


async def home_set_light(device: str, on: bool, brightness: Optional[int] = None) -> str:
    """
    Turn a light on or off; brightness in percent when turning it on.
    """
    light = find(load_devices(), device, "light")
    await _send(*light_message(light, on, brightness))

    if not on:
        return f"{light.name}: off."
    return f"{light.name}: on" + (f" at {brightness}%." if brightness is not None else ".")


async def home_lock(device: str) -> str:
    """
    Lock a door.
    """
    lock = find(load_devices(), device, "lock")
    await _send(*lock_message(lock, locked=True))
    return f"{lock.name}: locked."


async def home_unlock(device: str) -> str:
    """
    Unlock a door. HIGH risk: runs only after the owner approves it.
    """
    lock = find(load_devices(), device, "lock")
    await _send(*lock_message(lock, locked=False))
    return f"{lock.name}: unlocked."


class HomeSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="home",
            description="Controls the user's declared home devices (lights, locks) over MQTT.",
            version="1.0.0",
        )

    @staticmethod
    def configured() -> bool:
        try:
            return bool(load_devices())
        except DeviceConfigError as exc:
            # Reported by the configuration check too; no tools meanwhile.
            logger.error("Home devices disabled: %s", exc)
            return False

    @property
    def tools(self) -> List[Callable[..., Any]]:
        if not self.configured():
            return []
        return [home_list_devices, home_set_light, home_lock, home_unlock]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        # The registry lists tools from their metadata: none without devices.
        if not self.configured():
            return {}

        def meta(name: str, description: str, risk: RiskLevel, properties: Dict[str, Any], required: List[str], **extra: Any) -> ToolMetadata:
            return ToolMetadata(
                name=name,
                examples=EXAMPLES[name],
                description=description,
                risk_level=risk,
                permissions_required=["network:access"],
                network_access=True,
                max_runtime=PUBLISH_TIMEOUT_SECONDS + 10,
                max_output=2000,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                output_schema={"type": "string"},
                **extra,
            )

        return {
            "home_list_devices": meta(
                "home_list_devices",
                "List the user's home devices (lights, locks) with their ids.",
                RiskLevel.LOW,
                {},
                [],
            ),
            "home_set_light": meta(
                "home_set_light",
                "Turn a home light on or off (luce, lampada), optional brightness 0-100.",
                RiskLevel.LOW,
                {
                    "device": _DEVICE_ID,
                    "on": {"type": "boolean"},
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                ["device", "on"],
            ),
            "home_lock": meta(
                "home_lock",
                "Lock a door of the home (chiudi a chiave la porta).",
                RiskLevel.LOW,
                {"device": _DEVICE_ID},
                ["device"],
            ),
            "home_unlock": meta(
                "home_unlock",
                "Unlock a door of the home (apri la porta, serratura). Needs the owner's approval.",
                RiskLevel.HIGH,
                {"device": _DEVICE_ID},
                ["device"],
                requires_approval=True,
            ),
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        return (
            "For the user's lights and doors use the home_* tools with a device id "
            "from home_list_devices. Unlocking a door always waits for the user's approval."
        )


def get_skill() -> BaseSkill:
    return HomeSkill()


__all__ = [
    "HomeSkill",
    "get_skill",
    "home_list_devices",
    "home_lock",
    "home_set_light",
    "home_unlock",
]
