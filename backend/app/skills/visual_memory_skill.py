"""
@file backend/app/skills/visual_memory_skill.py
@description Native workspace-scoped visual memory skill.

Provides semantic image search and authenticated background indexing.
Filesystem-affecting operations are explicitly permission-gated.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from app.core.security import Permission

from .base import (
    BaseSkill,
    RiskLevel,
    SkillMetadata,
    ToolMetadata,
)
from .memory_skill import _require_memory_context


# ==============================================================================
# VISUAL MEMORY TOOLS
# ==============================================================================


def search_photos(
    query: str,
) -> str:
    """
    Search indexed images inside the authenticated workspace.
    """
    if not query.strip():
        raise ValueError(
            "Photo search query cannot be empty."
        )

    try:
        from app.workers.vision_indexer import search_images

        _, workspace_id = _require_memory_context()

        results = search_images(
            query=query,
            workspace_id=workspace_id,
        )

        ids = results.get(
            "ids",
            [],
        )

        if not ids or not ids[0]:
            return "No matching photos found."

        metadata = results.get(
            "metadatas",
            [],
        )

        if not metadata or not metadata[0]:
            return (
                "Matching photos were found "
                "without usable metadata."
            )

        matches = []

        for item in metadata[0]:
            path = item.get(
                "path",
                "[unknown path]",
            )

            matches.append(
                f"Path: {path}"
            )

        return (
            "Found matching photos:\n"
            + "\n".join(matches)
        )

    except Exception as exc:
        return f"Visual search error: {exc}"


def index_folder_for_vision(
    folder_path: str,
) -> str:
    """
    Queue authenticated visual indexing for a workspace folder.
    """
    if not folder_path.strip():
        raise ValueError(
            "Folder path cannot be empty."
        )

    session_id, _ = _require_memory_context()

    from app.core.celery_app import celery_app

    celery_app.send_task(
        "vision.index_folder",
        args=[
            session_id,
            folder_path,
        ],
    )

    return (
        "Visual indexing job queued successfully."
    )


# ==============================================================================
# VISUAL MEMORY SKILL
# ==============================================================================


class VisualMemorySkill(BaseSkill):
    """
    Provides authenticated semantic image search and folder indexing.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return visual-memory skill metadata.
        """
        return SkillMetadata(
            name="visual_memory",
            description=(
                "Provides workspace-scoped semantic photo search "
                "and authenticated image indexing."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return executable visual-memory tools.
        """
        return [
            search_photos,
            index_folder_for_vision,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return security and execution metadata for visual-memory tools.
        """
        return {
            "search_photos": ToolMetadata(
                name="search_photos",
                description=(
                    "Search indexed images inside the authenticated "
                    "workspace using semantic similarity."
                ),
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                permissions_required=[
                    Permission.READ_MEMORY.value,
                ],
                network_access=False,
                filesystem_access=False,
                max_runtime=30,
                max_output=8_000,
                max_cost=0.0,
                idempotent=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="default",
                audit_policy="standard",
            ),
            "index_folder_for_vision": ToolMetadata(
                name="index_folder_for_vision",
                description=(
                    "Queue semantic indexing for an authenticated "
                    "workspace folder."
                ),
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                permissions_required=[
                    Permission.FILESYSTEM_ACCESS.value,
                ],
                network_access=False,
                filesystem_access=True,
                max_runtime=60,
                max_output=2_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": ["folder_path"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="vision-indexing",
                audit_policy="standard",
            ),
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return visual-memory system instructions.
        """
        return (
            "You have access to authenticated visual memory. "
            "Use 'search_photos' to search images inside the current "
            "workspace. Use 'index_folder_for_vision' only when the "
            "user explicitly requests indexing. Filesystem access and "
            "human approval are enforced by the runtime."
        )


def get_skill() -> BaseSkill:
    """
    Create the visual-memory skill instance.
    """
    return VisualMemorySkill()