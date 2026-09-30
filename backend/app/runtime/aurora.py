"""
@file backend/app/runtime/aurora.py
@description Native compatibility facade for the A.U.R.O.R.A. Agent Engine.

This module replaces the former LangGraph-based runtime with the native
AgentRuntime execution kernel.

Compatibility is intentionally preserved through:
    get_aurora_app().ainvoke(...)

Existing callers can therefore migrate incrementally without retaining
LangGraph as an execution authority.

The native execution path is:

    Input -> AgentRuntime -> Native Worker -> Checker -> Durable Run State

No graph compiler, graph checkpoint, ToolNode, or LangGraph runtime is used.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional

from app.agent_engine.checker import AgentChecker
from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum


DEFAULT_SYSTEM_PRINCIPAL = Principal(
    id="system",
    role=RoleEnum.SYSTEM,
    workspace_id="system",
)


class NativeAuroraWorker:
    """
    Native worker adapter used by the Aurora compatibility facade.
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


class NativeAuroraApplication:
    """
    Compatibility application exposing an async invoke API.

    Internally all execution is delegated to AgentRuntime.
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
        """
        config = config or {}

        session_id = str(
            input_state.get(
                "session_id",
                "default_session",
            )
        )

        principal = input_state.get("principal")

        if principal is None:
            principal = DEFAULT_SYSTEM_PRINCIPAL

        if not isinstance(principal, Principal):
            raise ValueError(
                "Aurora invocation requires a valid Principal."
            )

        messages = input_state.get(
            "messages",
            [],
        )

        intent = input_state.get(
            "current_intent",
            self._extract_last_message(messages),
        )

        if not intent:
            raise ValueError(
                "Aurora invocation requires a non-empty task."
            )

        configurable = config.get(
            "configurable",
            {},
        )

        run_id = configurable.get(
            "thread_id"
        )

        if not run_id:
            run_id = None

        task = {
            "description": str(intent),
        }

        result = await self.runtime.execute_task(
            task=task,
            orchestrator=None,
            worker=self.worker,
            checker=self.checker,
            run_id=run_id,
            session_id=session_id,
            workspace_id=principal.workspace_id,
        )

        message = SimpleNamespace(
            content=result if result is not None else ""
        )

        return {
            "messages": [message],
            "session_id": session_id,
            "current_intent": str(intent),
            "principal": principal,
        }

    @staticmethod
    def _extract_last_message(
        messages: list[Any],
    ) -> str:
        """
        Extract textual content without requiring LangChain message classes.
        """
        if not messages:
            return ""

        last = messages[-1]

        if isinstance(last, dict):
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


_aurora_app: Optional[NativeAuroraApplication] = None


async def get_aurora_app() -> NativeAuroraApplication:
    """
    Return the singleton native Aurora application facade.
    """
    global _aurora_app

    if _aurora_app is None:
        _aurora_app = NativeAuroraApplication()

    return _aurora_app


async def run_aurora_agent(
    session_id: str,
    transcript: str,
    principal: Principal,
) -> Dict[str, Any]:
    """
    Execute one native Aurora interaction for the authenticated principal.
    """
    if not session_id:
        raise ValueError(
            "session_id is required"
        )

    if not transcript or not transcript.strip():
        raise ValueError(
            "transcript is required"
        )

    if not isinstance(principal, Principal):
        raise ValueError(
            "principal is required"
        )

    app = await get_aurora_app()

    return await app.ainvoke(
        {
            "messages": [
                SimpleNamespace(
                    content=transcript
                )
            ],
            "session_id": session_id,
            "current_intent": transcript,
            "principal": principal,
        },
        config={
            "configurable": {
                "thread_id": f"{session_id}:{principal.id}"
            }
        },
    )


__all__ = [
    "NativeAuroraApplication",
    "get_aurora_app",
    "run_aurora_agent",
]