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

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.checker import AgentChecker
from app.agent_engine.routing import (
    ModelRouter,
    Role,
    ensure_distinct_models,
    triage_role,
)
from app.agent_engine.runtime import AgentRuntime
from app.agent_engine.state.manager import AgentStateManager
from app.core.runtime_config import config_value
from app.core.security import Permission, Principal


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
        model_provider: ModelProvider,
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
        checker_model_name: Optional[str] = None,
        model_provider: Optional[ModelProvider] = None,
        checker_provider: Optional[ModelProvider] = None,
        router: Optional[ModelRouter] = None,
    ) -> None:
        """
        Build one self-contained AgentEngine instance.

        By default every task is routed by role (spec 4.1): triage picks the
        implementer role, the ModelRouter supplies that role's failover
        chain, and the Critic uses its own, independent chain.

        Args:
            model_name:
                Legacy single-model mode: one OpenAI model for every task.
            worker_system_prompt:
                Optional fixed worker system contract.
            runtime:
                Optional preconfigured AgentRuntime, primarily useful for
                tests and controlled dependency injection.
            checker_model_name:
                Critic model in single-model mode. Falls back to
                AEHUB_CHECKER_MODEL, then to the worker model (rejected).
            model_provider / checker_provider:
                Optional preconfigured providers (dependency injection).
            router:
                Optional preconfigured ModelRouter.

        Raises:
            RoutingConfigError: when the Critic would share a model with an
            Implementer (fail closed).
        """
        self.worker_system_prompt = (
            worker_system_prompt
            or (
                "You are the native ÆHub agent worker. "
                "Follow the task exactly, respect the trusted execution "
                "context, and return only the requested result."
            )
        )

        if model_provider is None and model_name != "default":
            model_provider = OpenAIAdapter(
                model_name=model_name,
            )

        self.router: Optional[ModelRouter] = None
        self.model_provider = model_provider

        if model_provider is not None:
            checker_provider = checker_provider or OpenAIAdapter(
                model_name=(
                    checker_model_name
                    or config_value("AEHUB_CHECKER_MODEL")
                    or model_provider.model_name
                ),
            )
            ensure_distinct_models(
                model_provider,
                checker_provider,
            )
        else:
            self.router = router or ModelRouter()
            checker_provider = (
                checker_provider
                or self.router.provider_for(Role.CRITIC)
            )

        self.worker = (
            NativeAgentWorker(
                model_provider=model_provider,
                system_prompt=self.worker_system_prompt,
            )
            if model_provider is not None
            else None
        )

        self.checker = AgentChecker(
            model_provider=checker_provider,
        )

        self.runtime = (
            runtime
            or AgentRuntime()
        )

    def worker_for(
        self,
        task: str,
    ) -> NativeAgentWorker:
        """
        Return the worker for a task: the fixed one in single-model mode,
        otherwise the failover chain of the role chosen by triage.
        """
        if self.worker is not None:
            return self.worker

        role = triage_role(task)

        return NativeAgentWorker(
            model_provider=self.router.provider_for(role),
            system_prompt=self.worker_system_prompt,
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
            worker=self.worker_for(str(intent)),
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

    async def spawn_subagent(
        self,
        parent_run_id: Optional[str],
        session_id: str,
        task: str,
        role: str,
        budget: float,
        principal: Principal,
        allowed_tools: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
        deadline: Optional[datetime] = None,
        result_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Delegate a task to a subagent of a running parent.

        The subagent uses the worker the triage picks for its task and the
        same independent Critic as every run; the runtime narrows its tools,
        permissions and budget to what the parent may use.
        """
        if not isinstance(principal, Principal):
            raise ValueError(
                "principal is required."
            )

        return await self.runtime.spawn_agent(
            parent_run_id=parent_run_id,
            child_run_id=f"run_{uuid4().hex}",
            task={"description": task},
            role=role,
            budget=budget,
            permissions=(
                list(permissions)
                if permissions is not None
                else [permission.value for permission in Permission]
            ),
            deadline=deadline,
            result_schema=result_schema or {},
            worker_provider=self.worker_for(task).model_provider,
            checker=self.checker,
            allowed_tools=allowed_tools,
            session_id=session_id,
            workspace_id=principal.workspace_id,
            principal=principal,
        )

    async def resume(
        self,
        run_id: str,
        session_id: str,
        principal: Principal,
    ) -> Any:
        """
        Resume an existing run, typically after a human approval decision.

        The run must already exist for this session and Principal: resume
        never starts a new task. The persisted task and parked tool call are
        authoritative.
        """
        if not run_id or not session_id:
            raise ValueError(
                "run_id and session_id are required."
            )

        if not isinstance(
            principal,
            Principal,
        ):
            raise ValueError(
                "principal is required."
            )

        existing = AgentStateManager.load_agent_run(
            run_id,
            session_id=session_id,
            workspace_id=principal.workspace_id,
            principal_id=principal.id,
        )

        if existing is None:
            raise LookupError(
                f"Run {run_id} does not exist."
            )

        # Triage is deterministic: the persisted task routes to the same role.
        persisted_task = (
            (existing.current_state or {})
            .get("worker_context", {})
            .get("task")
            or {}
        )

        return await self.runtime.execute_task(
            task={},
            orchestrator=None,
            worker=self.worker_for(
                str(persisted_task.get("description", ""))
                if isinstance(persisted_task, dict)
                else str(persisted_task)
            ),
            checker=self.checker,
            run_id=run_id,
            session_id=session_id,
            workspace_id=principal.workspace_id,
            principal=principal,
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


def reset_agent_engine() -> None:
    """
    Drop the engine so the next request builds one from the current model
    settings (M12). Runs already started keep the engine they hold.
    """
    global _agent_engine
    _agent_engine = None


__all__ = [
    "AgentEngine",
    "NativeAgentWorker",
    "get_agent_engine",
    "reset_agent_engine",
]