"""
@file backend/app/runtime/aurora.py
@description Native compatibility facade for the A.U.R.O.R.A. Agent Engine.

This module exposes the historical Aurora application interface while routing
all execution through the native AgentRuntime.

The compatibility layer intentionally avoids LangGraph as an execution
authority. A request is represented by an authenticated Principal and an
explicit execution run ID.

Execution path:

    Request -> NativeAuroraApplication -> AgentRuntime
            -> Native Worker -> ToolGateway -> Checker
            -> Durable Run State
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional
from uuid import uuid4

from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.checker import AgentChecker
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal


# ==============================================================================
# NATIVE WORKER
# ==============================================================================


class NativeAuroraWorker:
    """
    Native worker adapter used by the Aurora compatibility facade.

    The worker receives the complete trusted execution context from
    AgentRuntime and forwards it to the configured model provider.
    """

    def __init__(
        self,
        model_provider: OpenAIAdapter,
        system_prompt: str,
    ) -> None:
        self.model_provider = model_provider
        self.system_prompt = system_prompt

    async def generate(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate one worker step through the native ModelProvider interface.
        """
        worker_context = dict(context)

        worker_context["system_prompt"] = self.system_prompt
        worker_context.setdefault(
            "role",
            "aurora",
        )

        return await self.model_provider.generate(
            worker_context
        )


# ==============================================================================
# AURORA APPLICATION FACADE
# ==============================================================================


class NativeAuroraApplication:
    """
    Compatibility application exposing an async invoke API.

    All execution is delegated to AgentRuntime. No client-controlled
    identity or thread identifier is allowed to override the authenticated
    execution Principal.
    """

    def __init__(
        self,
        model_name: str = "default",
    ) -> None:
        self.model_provider = OpenAIAdapter(
            model_name=model_name,
        )

        self.worker = NativeAuroraWorker(
            model_provider=self.model_provider,
            system_prompt=(
                "You are A.U.R.O.R.A., the native ÆHub orchestration worker. "
                "Follow the task exactly, respect the execution context, and "
                "return only the requested result."
            ),
        )

        self.checker = AgentChecker(
            model_provider=OpenAIAdapter(
                model_name=model_name,
            )
        )

        self.runtime = AgentRuntime()

    async def ainvoke(
        self,
        input_state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke the native AgentRuntime using the historical Aurora state shape.

        The run identifier may be supplied explicitly by a trusted caller for
        resume/recovery semantics. A client thread identifier is never treated
        as an execution run identifier.
        """
        config = config or {}

        session_id = str(
            input_state.get(
                "session_id",
                "",
            )
        )

        if not session_id:
            raise ValueError(
                "Aurora invocation requires a valid session_id."
            )

        principal = input_state.get(
            "principal"
        )

        if not isinstance(
            principal,
            Principal,
        ):
            raise ValueError(
                "Aurora invocation requires a valid Principal."
            )

        if (
            not principal.workspace_id
            or not principal.workspace_id.strip()
        ):
            raise ValueError(
                "Aurora invocation requires a valid principal workspace."
            )

        messages = input_state.get(
            "messages",
            [],
        )

        intent = input_state.get(
            "current_intent",
            self._extract_last_message(
                messages
            ),
        )

        if (
            not intent
            or not str(intent).strip()
        ):
            raise ValueError(
                "Aurora invocation requires a non-empty task."
            )

        configurable = config.get(
            "configurable",
            {},
        )

        run_id = (
            input_state.get(
                "run_id"
            )
            or configurable.get(
                "run_id"
            )
        )

        task = {
            "description": str(intent),
        }

        result = await self.runtime.execute_task(
            task=task,
            orchestrator=None,
            worker=self.worker,
            checker=self.checker,
            run_id=(
                str(run_id)
                if run_id
                else None
            ),
            session_id=session_id,
            workspace_id=principal.workspace_id,
            principal=principal,
        )

        message = SimpleNamespace(
            content=(
                result
                if result is not None
                else ""
            )
        )

        return {
            "messages": [
                message
            ],
            "session_id": session_id,
            "current_intent": str(
                intent
            ),
            "principal": principal,
            "run_id": (
                str(run_id)
                if run_id
                else None
            ),
        }

    @staticmethod
    def _extract_last_message(
        messages: list[Any],
    ) -> str:
        """
        Extract textual content without requiring framework-specific message
        classes.
        """
        if not messages:
            return ""

        last = messages[-1]

        if isinstance(
            last,
            dict,
        ):
            return str(
                last.get(
                    "content",
                    "",
                )
            )

        return str(
            getattr(
                last,
                "content",
                last,
            )
        )


# ==============================================================================
# SINGLETON COMPATIBILITY ACCESSOR
# ==============================================================================


_aurora_app: Optional[
    NativeAuroraApplication
] = None


async def get_aurora_app() -> NativeAuroraApplication:
    """
    Return the singleton native Aurora application facade.
    """
    global _aurora_app

    if _aurora_app is None:
        _aurora_app = NativeAuroraApplication()

    return _aurora_app


# ==============================================================================
# DIRECT AURORA EXECUTION ENTRY POINT
# ==============================================================================


async def run_aurora_agent(
    session_id: str,
    transcript: str,
    principal: Principal,
) -> Dict[str, Any]:
    """
    Execute one native Aurora interaction for the authenticated Principal.

    Every invocation receives a fresh execution run ID. Resume operations must
    explicitly provide the persisted run ID through the higher-level invoke
    interface instead of deriving it from session or thread identifiers.
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
                SimpleNamespace(
                    content=transcript,
                )
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
    "run_aurora_agent",
]