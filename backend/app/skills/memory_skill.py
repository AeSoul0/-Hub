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
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.memory.store import MemoryKind, MemoryStore

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


# ==============================================================================
# TRUSTED EXECUTION CONTEXT
# ==============================================================================


@dataclass(frozen=True)
class MemoryScope:
    """
    Trusted memory scope of the tool call in progress.

    trusted is False when the run context already holds untrusted content:
    whatever the model saves then may be attacker-influenced, so it is
    stored as untrusted and never becomes a preference or rule (M6).
    """

    session_id: str
    workspace_id: str
    principal_id: Optional[str] = None
    trusted: bool = True


_memory_context: contextvars.ContextVar[
    Optional[MemoryScope]
] = contextvars.ContextVar(
    "aehub_memory_context",
    default=None,
)


def set_memory_context(
    session_id: str,
    workspace_id: str,
    principal_id: Optional[str] = None,
    trusted: bool = True,
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
        MemoryScope(
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            trusted=trusted,
        )
    )


def clear_memory_context() -> None:
    """
    Clear the current memory execution context.
    """
    _memory_context.set(None)


def _require_memory_scope() -> MemoryScope:
    """
    Return the authenticated memory scope or fail closed.
    """
    scope = _memory_context.get()

    if scope is None:
        raise PermissionError(
            "Memory execution context is not available."
        )

    if not scope.session_id or not scope.workspace_id:
        raise PermissionError(
            "Memory execution context is incomplete."
        )

    return scope


def current_memory_scope() -> MemoryScope:
    """
    The authenticated scope of the tool call in progress, for other native
    skills that need the caller's workspace (fails closed outside a call).
    """
    return _require_memory_scope()


def _save(
    content: str,
    kind: MemoryKind,
    label: str,
) -> str:
    """
    Persist content in the long-term store of the authenticated principal.
    """
    if not content or not content.strip():
        raise ValueError(
            f"{label} memory content cannot be empty."
        )

    scope = _require_memory_scope()

    if not scope.principal_id:
        raise PermissionError(
            "Memory execution context has no principal."
        )

    MemoryStore(
        workspace_id=scope.workspace_id,
        principal_id=scope.principal_id,
    ).add(
        content.strip(),
        kind,
        trusted=scope.trusted,
        source="agent",
        session_id=scope.session_id,
    )

    suffix = "" if scope.trusted else " (stored as untrusted)"

    return f"{label} memory saved{suffix}: {content.strip()}"


# ==============================================================================
# NATIVE MEMORY TOOLS
# ==============================================================================


def save_semantic_memory(
    fact: str,
) -> str:
    """
    Persist a durable fact about the user or their projects.
    """
    return _save(fact, MemoryKind.FACT, "Semantic")


def save_procedural_memory(
    rule: str,
) -> str:
    """
    Persist a durable procedure or working rule.
    """
    return _save(rule, MemoryKind.RULE, "Procedural")


def save_user_preference(
    preference: str,
) -> str:
    """
    Persist a durable user preference (tone, language, habits).
    """
    return _save(preference, MemoryKind.PREFERENCE, "Preference")


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
                "Allows A.U.R.O.R.A. to persist facts, rules and user "
                "preferences that are recalled in later sessions."
            ),
            version="1.1.0",
        )

    @property
    def tools(self) -> List[Callable[..., Any]]:
        """
        Return the native executable tools exposed by this skill.
        """
        return [
            save_semantic_memory,
            save_procedural_memory,
            save_user_preference,
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
            "save_user_preference": ToolMetadata(
                name="save_user_preference",
                description="Stores a durable preference of the user.",
                risk_level=RiskLevel.LOW,
                permissions_required=[
                    "memory:write",
                ],
                input_schema={
                    "type": "object",
                    "properties": {
                        "preference": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": [
                        "preference",
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
            "preference, or procedure, use the appropriate memory tool; "
            "relevant memories from earlier sessions are recalled for you. "
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
    "current_memory_scope",
    "get_skill",
    "save_procedural_memory",
    "save_semantic_memory",
    "set_memory_context",
]