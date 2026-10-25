"""
@file backend/app/agent_engine/control.py
@description Run control: kill switch, spend limits and the monthly ledger.

- CancellationToken / RunRegistry: every live run registers a token. A run
  can be cancelled on its own, or all runs at once ("stop all"), which also
  halts new runs until resumed. Cancellation interrupts the awaited model
  call or tool, not only the next loop iteration.
- RunLimits: per-run cost cap and monthly spend cap (warning at 80%).
- SpendLedger: durable monthly model spend per principal.

ÆHub is single-user and local-first, so the registry is in-process.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Dict, List, Optional, TypeVar

from app.agent_engine.errors import RunCancelledError
from app.core.runtime_config import config_value


T = TypeVar("T")

# Time a cancelled step gets to unwind (kill its subprocess, write audit).
CANCEL_GRACE_SECONDS = 5.0


# ==============================================================================
# CANCELLATION
# ==============================================================================


class CancellationToken:
    """
    Cancellation flag that can also be awaited.
    """

    def __init__(self) -> None:
        self.is_cancelled = False
        self.reason: Optional[str] = None
        self._event: Optional[asyncio.Event] = None

    def cancel(self, reason: str = "Cancelled by user.") -> None:
        if self.is_cancelled:
            return

        self.is_cancelled = True
        self.reason = reason

        if self._event is not None:
            self._event.set()

    async def wait(self) -> None:
        if self._event is None:
            self._event = asyncio.Event()
            if self.is_cancelled:
                self._event.set()

        await self._event.wait()


async def run_interruptible(awaitable: Awaitable[T], token: Any) -> T:
    """
    Await a step, cancelling it as soon as the token is cancelled.

    Raises RunCancelledError when the token wins; the step task is cancelled
    and given CANCEL_GRACE_SECONDS to clean up.
    """
    if token is None:
        return await awaitable

    if getattr(token, "is_cancelled", False):
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise RunCancelledError(getattr(token, "reason", None) or "Run cancelled.")

    # Tokens without wait() (plain flags) can only be checked between steps.
    if not hasattr(token, "wait"):
        return await awaitable

    step = asyncio.ensure_future(awaitable)
    cancelled = asyncio.ensure_future(token.wait())

    try:
        done, _ = await asyncio.wait(
            {step, cancelled},
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:
        step.cancel()
        raise
    finally:
        if not cancelled.done():
            cancelled.cancel()

    if step in done:
        return step.result()

    step.cancel()

    try:
        await asyncio.wait_for(step, timeout=CANCEL_GRACE_SECONDS)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        pass

    raise RunCancelledError(token.reason or "Run cancelled.")


@dataclass
class LiveRun:
    run_id: str
    session_id: str
    workspace_id: str
    principal_id: str
    token: Any
    started_at: datetime


class RunRegistry:
    """
    Live runs of this process, for the kill switch.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: Dict[str, LiveRun] = {}
        self.halted = False
        self.halt_reason: Optional[str] = None

    def register(
        self,
        run_id: str,
        session_id: str,
        workspace_id: str,
        principal_id: str,
        token: Any = None,
    ) -> Any:
        token = token if token is not None else CancellationToken()

        with self._lock:
            self._runs[run_id] = LiveRun(
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal_id=principal_id,
                token=token,
                started_at=datetime.utcnow(),
            )

        return token

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def get(self, run_id: str) -> Optional[LiveRun]:
        with self._lock:
            return self._runs.get(run_id)

    def active(self, workspace_id: Optional[str] = None) -> List[LiveRun]:
        with self._lock:
            return [
                run
                for run in self._runs.values()
                if workspace_id is None or run.workspace_id == workspace_id
            ]

    def cancel(self, run_id: str, reason: str = "Cancelled by user.") -> bool:
        live = self.get(run_id)

        if live is None:
            return False

        live.token.cancel(reason)
        return True

    def stop_all(self, reason: str = "Stopped by the global kill switch.") -> int:
        """
        Cancel every live run and refuse new runs until resume().
        """
        with self._lock:
            self.halted = True
            self.halt_reason = reason
            runs = list(self._runs.values())

        for live in runs:
            live.token.cancel(reason)

        return len(runs)

    def resume(self) -> None:
        with self._lock:
            self.halted = False
            self.halt_reason = None


run_registry = RunRegistry()


# ==============================================================================
# LIMITS AND MONTHLY SPEND
# ==============================================================================


def _env_float(name: str, default: float) -> float:
    try:
        return float(config_value(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(config_value(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class RunLimits:
    """
    Per-run and monthly limits. Spend is in USD. Read on every run (Control
    Plane settings, then the environment) so a change applies without a
    restart. A limit of 0 disables it.
    """

    max_run_cost: float
    monthly_budget: float
    warning_ratio: float = 0.8

    # Active execution time; time spent waiting for an approval never counts.
    max_run_seconds: float = 900.0
    max_failed_tool_calls: int = 10
    max_files_modified: int = 20

    @classmethod
    def from_env(cls) -> "RunLimits":
        return cls(
            max_run_cost=_env_float("AEHUB_RUN_MAX_COST", 2.0),
            monthly_budget=_env_float("AEHUB_MONTHLY_BUDGET", 30.0),
            warning_ratio=_env_float("AEHUB_BUDGET_WARNING_RATIO", 0.8),
            max_run_seconds=_env_float("AEHUB_RUN_TIMEOUT_SECONDS", 900.0),
            max_failed_tool_calls=_env_int("AEHUB_RUN_MAX_FAILED_TOOL_CALLS", 10),
            max_files_modified=_env_int("AEHUB_RUN_MAX_FILES_MODIFIED", 20),
        )


def usage_view(usage: Dict[str, Any], active_seconds: float = 0.0) -> Dict[str, Any]:
    """
    The run totals that the per-run limits apply to, as the interface shows
    them next to those limits (F2).
    """
    return {
        "cost": round(float(usage.get("cost") or 0.0), 6),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "model_calls": int(usage.get("model_calls") or 0),
        "tool_calls": int(usage.get("tool_calls") or 0),
        "failed_tool_calls": int(usage.get("failed_tool_calls") or 0),
        "files_modified": len(usage.get("files_modified") or []),
        "active_seconds": round(float(active_seconds), 1),
    }


def current_period(now: Optional[datetime] = None) -> str:
    return (now or datetime.utcnow()).strftime("%Y-%m")


class SpendLedger:
    """
    Durable model spend per principal and calendar month.
    """

    @staticmethod
    def spent(principal_id: str, period: Optional[str] = None) -> float:
        from app.core.db import SessionLocal
        from app.domain.models.runtime_state import MonthlySpend

        with SessionLocal() as db:
            row = (
                db.query(MonthlySpend)
                .filter(
                    MonthlySpend.principal_id == principal_id,
                    MonthlySpend.period == (period or current_period()),
                )
                .first()
            )

            return float(row.spent) if row else 0.0

    @staticmethod
    def add(principal_id: str, cost: float, period: Optional[str] = None) -> float:
        """
        Add spend and return the month total. Spend that already happened is
        always recorded, even past the cap: the cap blocks the next call.
        """
        from app.core.db import SessionLocal
        from app.domain.models.runtime_state import MonthlySpend

        period = period or current_period()

        with SessionLocal() as db:
            row = (
                db.query(MonthlySpend)
                .filter(
                    MonthlySpend.principal_id == principal_id,
                    MonthlySpend.period == period,
                )
                .with_for_update()
                .first()
            )

            if row is None:
                row = MonthlySpend(
                    principal_id=principal_id,
                    period=period,
                    spent=0.0,
                )
                db.add(row)

            row.spent = float(row.spent or 0.0) + max(0.0, cost)
            total = row.spent
            db.commit()

            return total


__all__ = [
    "CANCEL_GRACE_SECONDS",
    "CancellationToken",
    "LiveRun",
    "RunLimits",
    "RunRegistry",
    "SpendLedger",
    "current_period",
    "run_interruptible",
    "run_registry",
]
