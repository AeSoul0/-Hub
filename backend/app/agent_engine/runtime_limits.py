"""
@file backend/app/agent_engine/runtime_limits.py
@description Limits of a run (part of AgentRuntime, Q1): capabilities,
run limits, spend against the run and monthly budget, the stop of a run, and
the live usage the Runs page reads while a run executes.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.agent_engine.control import (
    RunLimits,
    SpendLedger,
    usage_view,
)
from app.agent_engine.errors import (
    BudgetExceededError,
    RunCancelledError,
    RunInterrupted,
    RunLimitExceededError,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.models import (
    AgentRun,
    AgentRunStatus,
    Observation,
    ToolProposal,
)
from app.core.security import (
    SubagentCapabilitySet,
)


logger = logging.getLogger(__name__)


def _usd(amount: float) -> str:
    """
    A spending cap as configured: 2 -> "2", 0.001 -> "0.001" (not "0.00").
    """
    return f"{amount:.6f}".rstrip("0").rstrip(".")


# Active execution time per run in this process: (seconds already recorded,
# start of the current segment). A run parked in WAITING_APPROVAL is not
# executing, so the wait never counts toward AEHUB_RUN_TIMEOUT_SECONDS.
_ACTIVE_SEGMENTS: Dict[str, Tuple[float, float]] = {}


# The usage totals of the runs executing in this process, kept by reference:
# the live view reads them between saves (F2).
_LIVE_USAGE: Dict[str, Dict[str, Any]] = {}


def live_active_seconds(run_id: str, recorded: float = 0.0) -> float:
    """
    Seconds a run has spent executing, across resumes; `recorded` when it
    is not executing in this process.
    """
    segment = _ACTIVE_SEGMENTS.get(run_id)

    if segment is None:
        return recorded

    before, started = segment

    return before + (time.monotonic() - started)


def live_usage(run_id: str, recorded: Dict[str, Any]) -> Dict[str, Any]:
    """
    The current totals of a run executing in this process, else `recorded`
    (its last saved totals).
    """
    usage = _LIVE_USAGE.get(run_id, recorded)

    return usage_view(
        usage,
        live_active_seconds(run_id, float(usage.get("active_seconds") or 0.0)),
    )


def _active_seconds(agent_run: AgentRun) -> float:
    return live_active_seconds(
        agent_run.run_id,
        float(agent_run.usage.get("active_seconds", 0.0)),
    )


def _usage_now(agent_run: AgentRun) -> Dict[str, Any]:
    """
    Run totals for the live events, so the interface follows the limits.
    """
    return usage_view(agent_run.usage, _active_seconds(agent_run))


class LimitsMixin:
    """
    Run limits for AgentRuntime: what a subagent may do, the per-run limits,
    the checks before and after each tool call, spend and usage, and the
    stop of a run when a limit or a cancellation ends it.
    """

    @staticmethod
    def _capabilities(
        worker_context: Dict[str, Any],
    ) -> Optional[SubagentCapabilitySet]:
        """
        The delegated capability set of a subagent run, None for a top-level run.
        """
        data = worker_context.get("subagent_capabilities")

        return SubagentCapabilitySet(**data) if data else None

    @staticmethod
    def _run_limits(
        worker_context: Dict[str, Any],
    ) -> RunLimits:
        """
        Limits from the environment, with a subagent's run budget capped by
        what its parent had left. With no run cost cap (0) the subagent's
        own budget is its cap.
        """
        limits = RunLimits.from_env()
        max_cost = worker_context.get("max_cost")

        if max_cost is not None:
            limits = dataclasses.replace(
                limits,
                max_run_cost=(
                    min(limits.max_run_cost, float(max_cost))
                    if limits.max_run_cost > 0
                    else float(max_cost)
                ),
            )

        return limits

    @classmethod
    def _file_target(
        cls,
        proposal: ToolProposal,
    ) -> Optional[str]:
        """
        The file a call would change, for tools that modify files.
        """
        try:
            spec = cls._build_tool_spec(proposal.tool_name)
        except ValueError:
            return None

        if not spec.modifies_files:
            return None

        arguments = proposal.arguments or {}

        return str(
            arguments.get("path")
            or arguments.get("file_path")
            or f"{proposal.tool_name}:{proposal.tool_call_id}"
        )

    @classmethod
    def _check_before_tool(
        cls,
        agent_run: AgentRun,
        proposal: ToolProposal,
        limits: RunLimits,
    ) -> Optional[RunLimitExceededError]:
        """
        Refuse a call that would change one file more than the run allows.
        """
        target = cls._file_target(proposal)
        modified = list(agent_run.usage.get("files_modified") or [])

        if (
            target is not None
            and target not in modified
            and limits.max_files_modified > 0
            and len(modified) >= limits.max_files_modified
        ):
            return RunLimitExceededError(
                f"Modified files limit reached: {len(modified)} of "
                f"{limits.max_files_modified}; '{proposal.tool_name}' was not run."
            )

        return None

    @staticmethod
    def _record_effects(
        agent_run: AgentRun,
        observation: Observation,
        limits: RunLimits,
    ) -> Optional[RunLimitExceededError]:
        """
        Count failed calls and modified files; stop the run once failures
        reach the per-run limit (a run stuck on failing tools or tests).
        """
        if observation.modified_file:
            modified = list(agent_run.usage.get("files_modified") or [])

            if observation.modified_file not in modified:
                modified.append(observation.modified_file)

            agent_run.usage["files_modified"] = modified

        stop: Optional[RunLimitExceededError] = None

        if not observation.succeeded:
            failed = int(agent_run.usage.get("failed_tool_calls", 0)) + 1
            agent_run.usage["failed_tool_calls"] = failed

            if 0 < limits.max_failed_tool_calls <= failed:
                stop = RunLimitExceededError(
                    f"Failed tool calls limit reached: {failed} of "
                    f"{limits.max_failed_tool_calls}."
                )

        EventDispatcher().dispatch(
            "tool.completed",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            tool=observation.tool_name,
            details={
                "succeeded": bool(observation.succeeded),
                "usage": _usage_now(agent_run),
            },
        )

        return stop

    @staticmethod
    def _check_spend(
        agent_run: AgentRun,
        principal_id: str,
        limits: RunLimits,
    ) -> Optional[BudgetExceededError]:
        """
        Refuse the next model call once the run or the month is out of budget.

        The ledger is part of the budget boundary: if it cannot be read the
        call is refused (fail closed).
        """
        run_cost = float(agent_run.usage.get("cost", 0.0))

        if limits.max_run_cost > 0 and run_cost >= limits.max_run_cost:
            return BudgetExceededError(
                f"Run budget exhausted: {run_cost:.4f} USD of "
                f"{_usd(limits.max_run_cost)} USD."
            )

        try:
            month_spent = SpendLedger.spent(principal_id)
        except Exception as exc:  # noqa: BLE001 - fail closed: without the ledger no model call runs
            logger.error("Spend ledger unavailable, model calls blocked: %s", exc)
            return BudgetExceededError(
                "Spend ledger unavailable: model calls are blocked."
            )

        if month_spent >= limits.monthly_budget:
            return BudgetExceededError(
                f"Monthly budget exhausted: {month_spent:.4f} USD of "
                f"{_usd(limits.monthly_budget)} USD."
            )

        return None

    def _record_usage(
        self,
        agent_run: AgentRun,
        usage: Any,
        role: str,
        principal_id: str,
        limits: RunLimits,
    ) -> Optional[BudgetExceededError]:
        """
        Add one model call to the run totals and the monthly ledger, and
        return a stop when a limit is now reached.
        """
        if not isinstance(usage, dict):
            return None

        totals = agent_run.usage
        model = str(usage.get("model") or "unknown")
        tokens = int(usage.get("total_tokens") or 0)
        cost = float(usage.get("cost") or 0.0)

        totals["model_calls"] = int(totals.get("model_calls", 0)) + 1

        for key in ("input_tokens", "output_tokens", "total_tokens"):
            totals[key] = int(totals.get(key, 0)) + int(usage.get(key) or 0)

        totals["cost"] = round(float(totals.get("cost", 0.0)) + cost, 8)

        if usage.get("estimated"):
            totals["cost_estimated"] = True

        per_model = totals.setdefault("by_model", {}).setdefault(
            model,
            {"calls": 0, "total_tokens": 0, "cost": 0.0},
        )
        per_model["calls"] += 1
        per_model["total_tokens"] += tokens
        per_model["cost"] = round(per_model["cost"] + cost, 8)

        per_role = totals.setdefault("by_role", {}).setdefault(
            role,
            {"calls": 0, "total_tokens": 0, "cost": 0.0},
        )
        per_role["calls"] += 1
        per_role["total_tokens"] += tokens
        per_role["cost"] = round(per_role["cost"] + cost, 8)

        totals.setdefault("calls", []).append(
            {
                "at": datetime.utcnow().isoformat(),
                "role": role,
                "model": model,
                "total_tokens": tokens,
                "cost": cost,
            }
        )

        EventDispatcher().dispatch(
            "model.called",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            tokens=tokens,
            cost=cost,
            model=model,
            role=role,
            details={"usage": _usage_now(agent_run)},
        )

        try:
            month_spent = SpendLedger.add(principal_id, cost)
        except Exception as exc:  # noqa: BLE001 - fail closed: without the ledger no model call runs
            logger.error("Spend ledger unavailable, model calls blocked: %s", exc)
            return BudgetExceededError(
                "Spend ledger unavailable: model calls are blocked."
            )

        if (
            month_spent >= limits.monthly_budget * limits.warning_ratio
            and not totals.get("budget_warning")
        ):
            totals["budget_warning"] = True

            EventDispatcher().dispatch(
                "budget.warning",
                run_id=agent_run.run_id,
                session_id=agent_run.session_id,
                workspace_id=agent_run.workspace_id,
                cost=month_spent,
                details={"monthly_budget": limits.monthly_budget},
            )

        if limits.max_run_cost > 0 and totals["cost"] >= limits.max_run_cost:
            return BudgetExceededError(
                f"Run budget exhausted: {totals['cost']:.4f} USD of "
                f"{_usd(limits.max_run_cost)} USD."
            )

        if month_spent >= limits.monthly_budget:
            return BudgetExceededError(
                f"Monthly budget exhausted: {month_spent:.4f} USD of "
                f"{_usd(limits.monthly_budget)} USD."
            )

        return None

    def _stop_run(
        self,
        agent_run: AgentRun,
        reason: RunInterrupted,
        current_attempt: int,
        turn: int,
        worker_context: Dict[str, Any],
        last_feedback: Optional[str],
    ) -> Dict[str, Any]:
        """
        Close a run stopped by the kill switch, a spend limit or a run limit.
        """
        cancelled = isinstance(reason, RunCancelledError)
        limited = isinstance(reason, RunLimitExceededError)

        agent_run.status = (
            AgentRunStatus.CANCELLED
            if cancelled
            else AgentRunStatus.FAILED
        )
        agent_run.error = str(reason)
        agent_run.errors.append(agent_run.error)

        EventDispatcher().dispatch(
            "run.cancelled"
            if cancelled
            else "run.limit_exceeded"
            if limited
            else "budget.exceeded",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            cost=float(agent_run.usage.get("cost", 0.0)),
            details={"reason": agent_run.error},
        )

        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        return {
            "status": (
                "CANCELLED"
                if cancelled
                else "LIMIT_EXCEEDED"
                if limited
                else "BUDGET_EXCEEDED"
            ),
            "run_id": agent_run.run_id,
            "reason": agent_run.error,
            "usage": {
                key: agent_run.usage.get(key)
                for key in ("model_calls", "total_tokens", "cost")
            },
        }
