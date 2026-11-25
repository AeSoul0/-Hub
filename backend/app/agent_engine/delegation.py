"""
@file backend/app/agent_engine/delegation.py
@description Delegation from a run to its subagents (F8, ADR-029).

The runtime installs a DelegationScope for the duration of one tool call,
as it does for the memory scope; `delegate_task`
(app/skills/orchestration_skill.py) reads it to start a subagent of the run
in progress. The scope holds the parent's live totals, so every subagent's
cost is charged to its parent and the parent's run budget bounds the parent
and all of its subagents together.

Delegation is one level deep: a subagent has a scope with is_subagent set
and cannot delegate again.
"""

from __future__ import annotations

import contextvars
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.security import Principal

DELEGATE_TOOL = "delegate_task"

Delegator = Callable[..., Awaitable[Dict[str, Any]]]

# What a subagent may spend when it asks for no budget and its parent has no
# run cost cap (AEHUB_RUN_MAX_COST=0): half of the default 2 USD cap, as with
# a capped parent that has spent nothing. The monthly budget still applies.
UNCAPPED_SUBAGENT_BUDGET = 1.0


@dataclass
class DelegationScope:
    """
    The run that is calling a tool, as delegation needs it.

    `usage` is the parent's AgentRun.usage itself (also shown live), so a
    charge is visible at once and stops the parent at its next model call
    once the run budget is spent.
    """

    parent_run_id: str
    session_id: str
    workspace_id: str
    principal: Principal
    usage: Dict[str, Any]
    max_run_cost: float
    max_subagents: int
    delegate: Optional[Delegator] = None
    is_subagent: bool = False

    def remaining(self) -> float:
        """
        What the run has left to spend; infinite when it has no cost cap (0).
        """
        if self.max_run_cost <= 0:
            return math.inf

        return self.max_run_cost - float(self.usage.get("cost", 0.0))

    def started(self) -> int:
        return int(self.usage.get("subagents", 0))

    def count_started(self) -> None:
        self.usage["subagents"] = self.started() + 1

    def charge(self, cost: float) -> None:
        """
        Add a finished subagent's cost to the parent run. The monthly ledger
        already has it: the subagent recorded its own model calls.
        """
        cost = max(0.0, float(cost))
        self.usage["cost"] = round(float(self.usage.get("cost", 0.0)) + cost, 8)
        self.usage["subagent_cost"] = round(
            float(self.usage.get("subagent_cost", 0.0)) + cost,
            8,
        )


_scope: contextvars.ContextVar[Optional[DelegationScope]] = contextvars.ContextVar(
    "aehub_delegation_scope",
    default=None,
)


def set_delegation_scope(scope: Optional[DelegationScope]) -> None:
    """
    Install the scope of the tool call in progress (trusted runtime code only).
    """
    _scope.set(scope)


def clear_delegation_scope() -> None:
    _scope.set(None)


def current_delegation_scope() -> DelegationScope:
    """
    The scope of the tool call in progress; fails closed outside a run.
    """
    scope = _scope.get()

    if scope is None:
        raise PermissionError("Delegation is only available inside a run.")

    return scope


__all__ = [
    "DELEGATE_TOOL",
    "DelegationScope",
    "Delegator",
    "UNCAPPED_SUBAGENT_BUDGET",
    "clear_delegation_scope",
    "current_delegation_scope",
    "set_delegation_scope",
]
