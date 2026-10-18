"""
@file backend/app/agent_engine/application.py
@description Public application facade for the native ÆHub Agent Engine.

This module is the canonical entrypoint for agent execution inside the
backend. It composes the deterministic AgentRuntime, Worker adapter, model
provider, and independent Checker into one framework-agnostic application
boundary.

Architectural ownership:
- AgentEngine owns engine composition and public invocation semantics.
- AgentRuntime owns deterministic execution and lifecycle orchestration.
- ToolGateway owns side-effect authorization and execution boundaries.
- AgentChecker owns independent result verification.
- Model adapters own provider-specific LLM communication.

This layer must remain independent from HTTP, WebSocket, FastAPI, frontend
state, and legacy Aurora naming.

Compatibility:
The historical app/runtime/aurora.py module delegates to this application
facade and must not reimplement engine behavior.
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


class NativeAgentWorker:
    """
    Native worker adapter used by AgentEngine.

    The worker receives a trusted execution context from AgentRuntime and
    forwards it to the configured framework-independent ModelProvider.

    No HTTP request state, browser session, or client-controlled identity is
    introduced here.
    """

    def __init__(
        self,
        model_provider: OpenAIAdapter,
        system_prompt: str,
    ) -> None:
        """
        Initialize the worker with a model provider and fixed system contract.
        """
        self.model_provider = model_provider
        self.system_prompt = system_prompt

    async def generate(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate exactly one worker step through the model provider.
        """
        worker_context = dict(
            context
        )

        worker_context["system_prompt"] = (
            self.system_prompt
        )

        worker_context.setdefault(
            "role",
            "agent",
        )

        return await self.model_provider.generate(
            worker_context
        )


# ==============================================================================
# AGENT ENGINE APPLICATION FACADE
# ==============================================================================


class AgentEngine:
    """
    Canonical public facade for the native ÆHub Agent Engine.

    AgentEngine is deliberately small. It composes the engine components but
    does not duplicate their responsibilities.

    The important boundary is:

        caller
          -> AgentEngine
          -> AgentRuntime
          -> Worker / ToolGateway / Checker
          -> durable AgentRun state

    Callers must provide an authenticated Principal. The Principal remains
    trusted execution context and is propagated unchanged into AgentRuntime.
    """

    def __init__(
        self,
        model_name: str = "default",
        worker_system_prompt: Optional[str] = None,
        runtime: Optional[AgentRuntime] = None,
    ) -> None:
        """
        Build one self-contained AgentEngine instance.

        Args:
            model_name:
                Model identifier passed to the provider adapters.
            worker_system_prompt:
                Optional fixed worker system contract.
            runtime:
                Optional preconfigured AgentRuntime, primarily useful for
                tests and controlled dependency injection.
        """
        self.model_provider = OpenAIAdapter(
            model_name=model_name,
        )

        self.worker = NativeAgentWorker(
            model_provider=self.model_provider,
            system_prompt=(
                worker_system_prompt
                or (
                    "You are the native ÆHub agent worker. "
                    "Follow the task exactly, respect the trusted execution "
                    "context, and return only the requested result."
                )
            ),
        )

        self.checker = AgentChecker(
            model_provider=OpenAIAdapter(
                model_name=model_name,
            )
        )

        self.runtime = (
            runtime
            or AgentRuntime()
        )

    # ==========================================================================
    # PUBLIC INVOCATION
    # ==========================================================================

    async def ainvoke(
        self,
        input_state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke the native AgentRuntime using the compatibility state contract.

        The method accepts the existing message-oriented input shape so current
        frontend and API integrations can migrate without a disruptive rewrite.

        Security requirements:
        - session_id must be explicitly supplied;
        - Principal must be a trusted Principal instance;
        - Principal must contain a workspace binding;
        - client-provided thread identifiers are never treated as authority.
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
                "Agent invocation requires a valid session_id."
            )

        principal = input_state.get(
            "principal"
        )

        if not isinstance(
            principal,
            Principal,
        ):
            raise ValueError(
                "Agent invocation requires a valid Principal."
            )

        if (
            not principal.workspace_id
            or not principal.workspace_id.strip()
        ):
            raise ValueError(
                "Agent invocation requires a valid principal workspace."
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
                "Agent invocation requires a non-empty task."
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
            "description": str(
                intent
            ),
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
                message,
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

    async def run(
        self,
        session_id: str,
        task: str,
        principal: Principal,
    ) -> Dict[str, Any]:
        """
        Execute one new agent interaction with an explicit run identifier.

        This method is the preferred high-level API for future internal
        services. The legacy ainvoke() method remains available while existing
        application boundaries migrate to the canonical AgentEngine facade.
        """
        if not session_id:
            raise ValueError(
                "session_id is required."
            )

        if (
            not task
            or not task.strip()
        ):
            raise ValueError(
                "task is required."
            )

        if not isinstance(
            principal,
            Principal,
        ):
            raise ValueError(
                "principal is required."
            )

        run_id = f"run_{uuid4().hex}"

        return await self.ainvoke(
            {
                "messages": [
                    SimpleNamespace(
                        content=task,
                    )
                ],
                "session_id": session_id,
                "current_intent": task,
                "principal": principal,
                "run_id": run_id,
            },
            config={
                "configurable": {
                    "run_id": run_id,
                }
            },
        )

    # ==========================================================================
    # INPUT NORMALIZATION
    # ==========================================================================

    @staticmethod
    def _extract_last_message(
        messages: list[Any],
    ) -> str:
        """
        Extract textual content from the last message.

        The engine intentionally supports plain dictionaries and lightweight
        objects instead of depending on a framework-specific message class.
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
# SINGLETON ACCESSOR
# ==============================================================================


_agent_engine: Optional[
    AgentEngine
] = None


async def get_agent_engine() -> AgentEngine:
    """
    Return the process-local canonical AgentEngine instance.

    The engine is currently stateless at the object level; durable execution
    state belongs to AgentStateManager/PostgreSQL. The singleton therefore
    represents dependency composition rather than execution state.
    """
    global _agent_engine

    if _agent_engine is None:
        _agent_engine = AgentEngine()

    return _agent_engine


__all__ = [
    "AgentEngine",
    "NativeAgentWorker",
    "get_agent_engine",
]