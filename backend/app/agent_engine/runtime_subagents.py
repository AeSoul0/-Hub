"""
@file backend/app/agent_engine/runtime_subagents.py
@description Subagents of a run (part of AgentRuntime, Q1): a child run
sized by the resources of its task, with at most the parent's capabilities,
started through `delegate_task` (ADR-029).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.control import (
    RunLimits,
)
from app.agent_engine.errors import (
    BudgetExceededError,
    TaskTimeoutError,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.resources import ResourceManager
from app.agent_engine.routing import IMPLEMENTER_ROLES
from app.agent_engine.state.manager import AgentStateManager
from app.agents.subagents.base import SubagentFactory
from app.core.security import (
    ROLE_PERMISSIONS,
    Principal,
    SubagentCapabilitySet,
    workspace_policy,
)
from app.agent_engine.runtime_limits import (
    _usd,  # noqa: F401 - re-exported, imported from here before Q1
    live_active_seconds,  # noqa: F401 - re-exported, imported from here before Q1
    live_usage,  # noqa: F401 - re-exported (api/runs.py)
)




class SubagentsMixin:
    """
    Native subagent creation for AgentRuntime.
    """

    async def spawn_agent(
        self,
        parent_run_id: Optional[str],
        child_run_id: str,
        task: Dict[str, Any],
        role: str,
        budget: float,
        permissions: List[str],
        deadline: Optional[datetime],
        result_schema: Dict[str, Any],
        worker_provider: ModelProvider,
        checker: Any,
        allowed_tools: Optional[List[str]] = None,
        session_id: str = "",
        workspace_id: str = "",
        principal: Optional[Principal] = None,
    ) -> Any:
        """
        Run a native subagent with an explicitly bounded capability set.

        The child inherits the authenticated Principal and workspace rather
        than an implicit system identity, and can only narrow them:
        - tools: `allowed_tools` (default all) ∩ workspace policy, and every
          call still goes through the PolicyEngine and the ToolGateway;
        - permissions: the requested ones ∩ the Principal's role;
        - budget: at most what the parent run has left;
        - provenance: a child of a tainted parent starts tainted, so its HIGH
          calls need approval too.

        `worker_provider` and `checker` come from the engine routing, so the
        Critic stays independent from the worker.
        """
        if principal is None:
            raise PermissionError(
                "Authenticated Principal is required for subagent execution."
            )

        if not isinstance(principal, Principal):
            raise PermissionError(
                "Subagent Principal is invalid."
            )

        if principal.workspace_id != workspace_id:
            raise PermissionError(
                "Principal workspace does not match subagent workspace."
            )

        if budget <= 0:
            raise ValueError(
                "Subagent budget must be greater than zero."
            )

        if not workspace_id:
            raise ValueError(
                "workspace_id is required."
            )

        if not session_id:
            raise ValueError(
                "session_id is required."
            )

        if not child_run_id:
            raise ValueError(
                "child_run_id is required."
            )

        limits = RunLimits.from_env()
        # A run cost cap of 0 is no cap: the subagent gets what it asks for.
        parent_remaining = (
            limits.max_run_cost if limits.max_run_cost > 0 else math.inf
        )
        inherit_untrusted = False

        if parent_run_id:
            parent_run = AgentStateManager.load_agent_run(
                parent_run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal_id=principal.id,
            )

            if parent_run is None or parent_run.principal_id != principal.id:
                raise PermissionError(
                    "Parent run does not belong to the authenticated Principal."
                )

            parent_context = (parent_run.current_state or {}).get(
                "worker_context"
            ) or {}

            inherit_untrusted = bool(
                parent_context.get("untrusted_context")
            )

            # A subagent of a spoken task is a spoken task too: its HIGH
            # actions also wait for a human (ADR-021).
            if self._input_channel(parent_context) == "voice":
                task = {**task, "input_channel": "voice"}

            parent_cap = self._run_limits(parent_context).max_run_cost
            parent_remaining = (
                parent_cap - float(parent_run.usage.get("cost", 0.0))
                if parent_cap > 0
                else math.inf
            )

        child_budget = min(budget, parent_remaining)

        if child_budget <= 0:
            raise BudgetExceededError(
                "The parent run has no budget left for a subagent."
            )

        try:
            resource_profile = ResourceManager.allocate(
                task.get(
                    "description",
                    str(task),
                )
            )
        except Exception as exc:
            raise RuntimeError(
                "Unable to allocate resources for subagent execution."
            ) from exc

        runtime_seconds = resource_profile.max_runtime

        if deadline is not None:
            remaining = (
                deadline - datetime.utcnow()
            ).total_seconds()

            runtime_seconds = min(
                runtime_seconds,
                max(
                    0.0,
                    remaining,
                ),
            )

        if runtime_seconds <= 0:
            raise TaskTimeoutError(
                "Subagent deadline does not permit execution."
            )

        role_permissions = [
            permission.value
            for permission in ROLE_PERMISSIONS.get(principal.role, [])
        ]

        capability_set = SubagentCapabilitySet.intersect(
            parent=SubagentCapabilitySet(
                allowed_tools=["*"],
                allowed_scopes=[],
                max_budget=child_budget,
                max_runtime=int(runtime_seconds),
                workspace=workspace_id,
                permissions=role_permissions,
            ),
            delegated=SubagentCapabilitySet(
                allowed_tools=list(allowed_tools or ["*"]),
                allowed_scopes=[],
                max_budget=child_budget,
                max_runtime=int(runtime_seconds),
                workspace=workspace_id,
                permissions=list(permissions),
            ),
            policy=workspace_policy(workspace_id),
        )

        # The role is kept with the task, so the run tree shows it and a
        # resumed subagent goes back to the same worker (F8).
        if role in {item.value for item in IMPLEMENTER_ROLES}:
            task = {**task, "role": role}

        worker = SubagentFactory.create_subagent(
            role_name=role,
            system_prompt=(
                f"You are a specialized ÆHub subagent for role '{role}'. "
                "Operate strictly within the delegated capability set."
            ),
            tools=[],
            adapter=worker_provider,
            capabilities=capability_set,
        )

        # The Nucleo draws each subagent as a moon of its parent run (F1).
        EventDispatcher().dispatch(
            "subagent.spawned",
            run_id=child_run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            role=role,
        )

        from app.agent_engine.streaming import streaming_answer

        # A subagent's words are never the user's answer: no draft (N1).
        with streaming_answer(None):
            result = await self.execute_task(
                task=task,
                orchestrator=None,
                worker=worker,
                checker=checker,
                timeout=runtime_seconds,
                run_id=child_run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal=principal,
                capabilities=capability_set,
                max_cost=child_budget,
                inherit_untrusted=inherit_untrusted,
                parent_run_id=parent_run_id,
            )

        EventDispatcher().dispatch(
            "subagent.completed",
            run_id=child_run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            role=role,
            # A finished subagent returns its answer; a stopped one a status.
            details={
                "status": (
                    result.get("status") or "COMPLETED"
                    if isinstance(result, dict)
                    else "COMPLETED"
                ),
            },
        )

        return {
            "parent_run_id": parent_run_id,
            "child_run_id": child_run_id,
            "role": role,
            "result_schema": result_schema,
            "result": result,
        }
