"""
@file backend/app/runtime/aurora.py
@description Legacy Aurora compatibility facade for the native Agent Engine.

This module exists only to preserve the historical Aurora-facing API while the
codebase migrates to the canonical AgentEngine facade.

Canonical ownership:
    app.agent_engine.application.AgentEngine

This compatibility layer must remain thin:
- no duplicated runtime logic;
- no duplicated Worker implementation;
- no duplicated Checker construction;
- no duplicated execution policy;
- no independent agent state.

Future callers should import AgentEngine or get_agent_engine() directly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from app.agent_engine.application import (
    AgentEngine,
    NativeAgentWorker,
)
from app.core.security import Principal


# ==============================================================================
# COMPATIBILITY WORKER
# ==============================================================================


class NativeAuroraWorker(NativeAgentWorker):
    """
    Backward-compatible name for the canonical NativeAgentWorker.

    New code must use NativeAgentWorker directly.
    """

    pass


# ==============================================================================
# COMPATIBILITY APPLICATION
# ==============================================================================


class NativeAuroraApplication(AgentEngine):
    """
    Backward-compatible Aurora application name.

    All actual behavior is inherited from AgentEngine. Keeping this class
    preserves existing imports and tests while making AgentEngine the
    authoritative implementation.
    """

    pass


# ==============================================================================
# LEGACY SINGLETON
# ==============================================================================


_aurora_app: Optional[
    NativeAuroraApplication
] = None


async def get_aurora_app() -> NativeAuroraApplication:
    """
    Return the legacy Aurora facade backed by the canonical AgentEngine.

    This accessor exists for compatibility only. New internal code should use
    app.agent_engine.application.get_agent_engine().
    """
    global _aurora_app

    if _aurora_app is None:
        _aurora_app = NativeAuroraApplication()

    return _aurora_app


def reset_aurora_app() -> None:
    """
    Drop the facade so the next request builds it from the current model
    settings (M12).
    """
    global _aurora_app
    _aurora_app = None


# ==============================================================================
# LEGACY DIRECT EXECUTION ENTRYPOINT
# ==============================================================================


async def run_aurora_agent(
    session_id: str,
    transcript: str,
    principal: Principal,
) -> Dict[str, Any]:
    """
    Execute one authenticated agent interaction through the canonical engine.

    The function preserves the historical return contract while delegating all
    actual execution to NativeAuroraApplication -> AgentRuntime.
    """
    if not session_id:
        raise ValueError(
            "session_id is required."
        )

    if (
        not transcript
        or not transcript.strip()
    ):
        raise ValueError(
            "transcript is required."
        )

    if not isinstance(
        principal,
        Principal,
    ):
        raise ValueError(
            "principal is required."
        )

    app = await get_aurora_app()

    run_id = (
        f"run_{uuid4().hex}"
    )

    return await app.ainvoke(
        {
            "messages": [
                {
                    "content": transcript,
                }
            ],
            "session_id": session_id,
            "current_intent": transcript,
            "principal": principal,
            "run_id": run_id,
        },
        config={
            "configurable": {
                "run_id": run_id,
            }
        },
    )


__all__ = [
    "NativeAuroraApplication",
    "NativeAuroraWorker",
    "get_aurora_app",
    "reset_aurora_app",
    "run_aurora_agent",
]