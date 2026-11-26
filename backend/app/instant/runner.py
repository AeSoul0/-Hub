"""
@file backend/app/instant/runner.py
@description Runs an instant command before the engine is even started (V1, ADR-035).

try_instant() is called first for every text or spoken command. When the
sentence is a recognized simple command, the tool runs at once through the
Tool Gateway (policy, audit) and the answer is a fixed sentence in the
language the user spoke: no model, no Critic, no cost. Otherwise it returns
None and the command goes to the engine unchanged.

A command whose tool needs an approval, or a tool not available here (no
apps listed, ÆHub in a container, no home devices), is left to the engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.runtime_config import config_value
from app.instant.apps import configured_apps
from app.instant.matcher import InstantCommand, match

logger = logging.getLogger(__name__)

SETTING = "AEHUB_INSTANT_COMMANDS"

REPLIES: Dict[str, Dict[str, str]] = {
    "it": {
        "open_app": "Apro {name}.",
        "open_folder": "Apro la cartella {name}.",
        "light_on": "{name}: luce accesa.",
        "light_off": "{name}: luce spenta.",
        "locked": "{name}: chiusa a chiave.",
        "failed": "Non ci sono riuscita: {error}",
    },
    "en": {
        "open_app": "Opening {name}.",
        "open_folder": "Opening the {name} folder.",
        "light_on": "{name}: light on.",
        "light_off": "{name}: light off.",
        "locked": "{name}: locked.",
        "failed": "I couldn't do it: {error}",
    },
}


def enabled() -> bool:
    return (config_value(SETTING) or "on") == "on"


def _home_devices() -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """(id, name) of the declared lights and locks; none when the file is invalid."""
    from app.home.devices import DeviceConfigError, load_devices

    try:
        devices = load_devices()
    except DeviceConfigError:
        return [], []
    lights = [(device.id, device.name) for device in devices.values() if device.type == "light"]
    locks = [(device.id, device.name) for device in devices.values() if device.type == "lock"]
    return lights, locks


def recognize(text: str) -> Optional[InstantCommand]:
    """The instant command the text is, against what the user declared, or None."""
    if not enabled():
        return None
    lights, locks = _home_devices()
    return match(text, apps=configured_apps(), lights=lights, locks=locks)


async def try_instant(
    text: str,
    principal: Any,
    session_id: str,
    input_channel: str = "text",
) -> Optional[Dict[str, Any]]:
    """
    Run the text as an instant command. Returns the reply and what was done,
    or None when the engine must handle it.
    """
    from app.agent_engine.errors import ApprovalRequiredError
    from app.runtime.direct_tool import needs_approval, run_tool, tool_spec

    started = time.perf_counter()
    command = recognize(text)
    if command is None:
        return None

    try:
        spec = tool_spec(command.tool)
    except ValueError:
        return None  # the tool is not offered here: the engine explains
    if needs_approval(spec):
        return None

    try:
        result = await run_tool(
            principal,
            command.tool,
            command.arguments,
            session_id=session_id,
            run_id=f"instant-{uuid.uuid4().hex}",
            call_id=f"instant-{command.tool}",
            input_channel=input_channel,
        )
    except ApprovalRequiredError:
        # The policy wants a human for this one: the engine's run asks.
        return None

    replies = REPLIES[command.language]
    if result.success:
        text_out = replies[command.reply].format(name=command.name)
    else:
        error = (result.error or "").strip() or ("errore sconosciuto." if command.language == "it" else "unknown error.")
        text_out = replies["failed"].format(error=error)
        logger.info("Instant command %s failed: %s", command.tool, error)

    return {
        "text": text_out,
        "tool": command.tool,
        "arguments": command.arguments,
        "success": bool(result.success),
        "audit_id": getattr(result, "audit_id", None),
        "ms": round((time.perf_counter() - started) * 1000),
    }


__all__ = ["REPLIES", "SETTING", "enabled", "recognize", "try_instant"]
