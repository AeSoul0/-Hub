"""
@file backend/app/skills/interface_skill.py
@description The app itself, as tools of Aurora (ADR-034): change the
interface language and turn the notice about the voice and interface
languages on or off.

Both are ordinary settings (AEHUB_UI_LANGUAGE, AEHUB_VOICE_LANGUAGE_WARNING):
saved through settings_service, so they are validated and written to the
audit chain like a change from IMPOSTAZIONI, by the principal of the run.
The pages hear an `interface.changed` event and switch at once.

Low risk: nothing leaves the computer and the change is undone the same way.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from app.core.interface import LANGUAGE_NAMES, LANGUAGE_SETTING, LANGUAGES, WARNING_SETTING, interface_state

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


SKILL_NAME = "interface"


def _save(changes: Dict[str, str]) -> None:
    from app.core.db import SessionLocal
    from app.core.settings_service import save_settings

    from .memory_skill import current_memory_scope

    scope = current_memory_scope()

    with SessionLocal() as db:
        save_settings(
            db,
            changes,
            principal_id=scope.principal_id or "agent",
            workspace_id=scope.workspace_id,
        )


async def _announce() -> None:
    from app.core.event_bus import event_bus

    from .memory_skill import current_memory_scope

    scope = current_memory_scope()
    await event_bus.publish(
        scope.session_id,
        "interface.changed",
        interface_state(),
        workspace_id=scope.workspace_id,
    )


async def set_interface_language(language: str) -> str:
    """
    Show the app in another language, from the next page view on.
    """
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise ValueError(f"The interface is available in: {', '.join(LANGUAGES)}.")

    _save({LANGUAGE_SETTING: language})
    await _announce()
    return f"The interface is now in {LANGUAGE_NAMES[language]}."


async def set_voice_language_warning(enabled: bool) -> str:
    """
    Show (or stop showing) the notice when the voice and the interface speak
    different languages.
    """
    _save({WARNING_SETTING: "on" if enabled else "off"})
    await _announce()
    return (
        "The notice about the voice and interface languages is on again."
        if enabled
        else "The notice about the voice and interface languages is off."
    )


class InterfaceSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name=SKILL_NAME,
            description="The app itself: its language and the notice about the voice language.",
            version="1.0.0",
            author="ÆHub",
        )

    @property
    def tools(self) -> List[Callable]:
        return [set_interface_language, set_voice_language_warning]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "set_interface_language": ToolMetadata(
                name="set_interface_language",
                description="Change the language of the ÆHub interface (the pages of the app).",
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "enum": list(LANGUAGES),
                            "description": "en: English, it: Italian.",
                        },
                    },
                    "required": ["language"],
                    "additionalProperties": False,
                },
                examples=[
                    "change the language of the app interface to English Italian",
                    "cambia la lingua dell'app dell'interfaccia in inglese italiano",
                    "metti l'app in italiano, switch the app to English",
                ],
            ),
            "set_voice_language_warning": ToolMetadata(
                name="set_voice_language_warning",
                description=(
                    "Turn on or off the notice shown when the chosen voice and the interface speak "
                    "different languages."
                ),
                risk_level=RiskLevel.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "description": "true shows the notice again."},
                    },
                    "required": ["enabled"],
                    "additionalProperties": False,
                },
                examples=[
                    "show again the warning notice popup about the voice language",
                    "riattiva l'avviso il popup della lingua della voce, non mostrare più l'avviso",
                ],
            ),
        }


_skill = InterfaceSkill()


def get_skill() -> InterfaceSkill:
    return _skill


__all__ = ["InterfaceSkill", "SKILL_NAME", "get_skill", "set_interface_language", "set_voice_language_warning"]
