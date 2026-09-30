"""
@file backend/app/skills/memory_skill.py
@description Native memory skill for the A.U.R.O.R.A. Agent Engine.

This module exposes memory operations as framework-agnostic Python callables.
Execution context is supplied only by the trusted AgentRuntime and contains
the authenticated session and workspace boundaries.

No LangChain decorators or implicit default session are used.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.memory.manager import AuroraMemoryManager

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


# ==============================================================================
# TRUSTED EXECUTION CONTEXT
# ==============================================================================


_memory_context: contextvars.ContextVar[
    Optional[Tuple[str, str]]
] = contextvars.ContextVar(
    "aehub_memory_context",
    default=None,
)


def set_memory_context(
    session_id: str,
    workspace_id: str,
) -> None:
    """
    Install the authenticated memory scope for the current execution context.

    This function is intended to be called only by trusted runtime code.
    """
    if not session_id:
        raise ValueError(
            "Memory session_id is required."
        )

    if not workspace_id:
        raise ValueError(
            "Memory workspace_id is required."
        )

    _memory_context.set(
        (
            session_id,
            workspace_id,
        )
    )


def clear_memory_context() -> None:
    """
    Clear the current memory execution context.
    """
    _memory_context.set(None)


def _require_memory_context() -> Tuple[str, str]:
    """
    Return the authenticated memory scope or fail closed.
    """
    context = _memory_context.get()

    if context is None:
        raise PermissionError(
            "Memory execution context is not available."
        )

    session_id, workspace_id = context

    if not session_id or not workspace_id:
        raise PermissionError(
            "Memory execution context is incomplete."
        )

    return session_id, workspace_id


def _build_manager() -> AuroraMemoryManager:
    """
    Construct a memory manager bound to the trusted execution scope.
    """
    session_id, workspace_id = _require_memory_context()

    return AuroraMemoryManager(
        session_id=session_id,
        workspace_id=workspace_id,
    )


# ==============================================================================
# NATIVE MEMORY TOOLS
# ==============================================================================


def save_semantic_memory(
    fact: str,
) -> str:
    """
    Persist a semantic fact inside the authenticated workspace.
    """
    if not fact or not fact.strip():
        raise ValueError(
            "Semantic memory content cannot be empty."
        )

    manager = _build_manager()

    manager.save_semantic(
        fact.strip()
    )

    return f"Semantic memory saved: {fact.strip()}"


def save_procedural_memory(
    rule: str,
) -> str:
    """
    Persist a procedural rule inside the authenticated workspace.
    """
    if not rule or not rule.strip():
        raise ValueError(
            "Procedural memory content cannot be empty."
        )

    manager = _build_manager()

    manager.save_procedural(
        rule.strip()
    )

    return f"Procedural memory saved: {rule.strip()}"


# ==============================================================================
# SKILL DEFINITION
# ==============================================================================


class MemorySkill(BaseSkill):
    """
    Native A.U.R.O.R.A. memory skill.

    The skill only exposes explicitly registered callables and security
    metadata. Runtime identity is never inferred from a global default.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return public metadata describing this skill.
        """
        return SkillMetadata(
            name="memory",
            description=(
                "Allows A.U.R.O.R.A. to persist semantic and procedural "
                "memories inside the authenticated workspace."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable[..., Any]]:
        """
        Return the native executable tools exposed by this skill.
        """
        return [
            save_semantic_memory,
            save_procedural_memory,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return security and runtime metadata for each exposed tool.
        """
        return {
            "save_semantic_memory": ToolMetadata(
                name="save_semantic_memory",
                description="Stores an authenticated semantic memory.",
                risk_level=RiskLevel.LOW,
                permissions_required=[
                    "memory:write",
                ],
                input_schema={
                    "type": "object",
                    "properties": {
                        "fact": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": [
                        "fact",
                    ],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                max_output=2000,
                idempotent=False,
                audit_policy="standard",
            ),
            "save_procedural_memory": ToolMetadata(
                name="save_procedural_memory",
                description="Stores an authenticated procedural memory.",
                risk_level=RiskLevel.LOW,
                permissions_required=[
                    "memory:write",
                ],
                input_schema={
                    "type": "object",
                    "properties": {
                        "rule": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": [
                        "rule",
                    ],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                max_output=2000,
                idempotent=False,
                audit_policy="standard",
            ),
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return the memory-specific system prompt extension.
        """
        return (
            "You have access to a long-term Memory system. "
            "When the user explicitly asks you to remember a durable fact, "
            "preference, or procedure, use the appropriate memory tool. "
            "Do not persist transient conversational context."
        )


def get_skill() -> BaseSkill:
    """
    Return the initialized MemorySkill instance.
    """
    return MemorySkill()


__all__ = [
    "MemorySkill",
    "clear_memory_context",
    "get_skill",
    "save_procedural_memory",
    "save_semantic_memory",
    "set_memory_context",
]