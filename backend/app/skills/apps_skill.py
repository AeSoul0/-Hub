"""
@file backend/app/skills/apps_skill.py
@description Opens the user's own apps and folders on this computer (V1, ADR-035).

    open_app      MEDIUM   start an app from the owner's list (AEHUB_APPS)
    open_folder   LOW      open Downloads, Documents, Desktop... in the file manager

The model names an app from the list, never a program or a command line, so
it can start nothing the owner did not choose. The same tools serve the
instant commands, which call them through the Tool Gateway without a model.
Inside a container (Docker) the skill offers no tools: the apps are on the
host, out of reach.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List

from app.instant.apps import FOLDERS, configured_apps, in_container, launch, open_folder as open_known_folder

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata

# Words that pick these tools in the skill index, Italian and English.
EXAMPLES = {
    "open_app": ["apri", "avvia", "lancia", "app", "programma", "open", "launch", "start", "app", "program"],
    "open_folder": ["apri la cartella", "cartella", "download", "documenti", "open folder", "folder", "downloads", "documents"],
}


async def open_app(app: str) -> str:
    """
    Open one of the user's apps by the name in their list.
    """
    apps = configured_apps()
    command = apps.get(app.strip().lower())
    if command is None:
        names = ", ".join(sorted(apps)) or "none"
        return f"'{app}' is not in the user's app list (available: {names})."
    await asyncio.to_thread(launch, command)
    return f"Opened {app.strip()}."


async def open_folder(folder: str) -> str:
    """
    Open a known folder (Downloads, Documents, Desktop, Pictures, Music, Videos).
    """
    path = await asyncio.to_thread(open_known_folder, folder)
    return f"Opened the folder {path}."


class AppsSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="apps",
            description="Opens the user's own apps and folders on this computer.",
            version="1.0.0",
        )

    @staticmethod
    def available() -> bool:
        return not in_container()

    @property
    def tools(self) -> List[Callable[..., Any]]:
        if not self.available():
            return []
        return [open_app, open_folder] if configured_apps() else [open_folder]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        if not self.available():
            return {}

        def meta(name: str, description: str, risk: RiskLevel, properties: Dict[str, Any]) -> ToolMetadata:
            return ToolMetadata(
                name=name,
                examples=EXAMPLES[name],
                description=description,
                risk_level=risk,
                permissions_required=["tool:execute:safe"],
                max_runtime=15,
                max_output=500,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
                output_schema={"type": "string"},
            )

        tools = {
            "open_folder": meta(
                "open_folder",
                "Open a folder of the user (Downloads, Documents, Desktop, Pictures, Music, Videos) in the file manager.",
                RiskLevel.LOW,
                {"folder": {"type": "string", "enum": sorted(FOLDERS)}},
            ),
        }
        apps = configured_apps()
        if apps:
            tools["open_app"] = meta(
                "open_app",
                "Open one of the user's apps on this computer (apri Spotify). Only names from the list.",
                RiskLevel.MEDIUM,
                {"app": {"type": "string", "enum": sorted(apps)}},
            )
        return tools


def get_skill() -> BaseSkill:
    return AppsSkill()


__all__ = ["AppsSkill", "get_skill", "open_app", "open_folder"]
