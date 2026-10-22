"""
@file backend/app/api/runs.py
@description Run control and spend dashboard API (roadmap M4).

POST /api/runs/{run_id}/cancel   cancel one live run (owner or admin)
POST /api/runs/stop-all          kill switch: cancel every live run and
                                 refuse new ones until resumed (admin)
POST /api/runs/resume            lift the kill switch (admin)
GET  /api/runs/live              live runs of the workspace + kill switch state
GET  /api/runs/stats             spend dashboard of the workspace
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent_engine.control import (
    RunLimits,
    SpendLedger,
    current_period,
    run_registry,
)
from app.core.security import Principal, RoleEnum, resolve_principal


router = APIRouter(
    prefix="/api/runs",
    tags=["runs"],
)

_CONTROL_ROLES = {RoleEnum.ADMIN, RoleEnum.SYSTEM}
_FAILED_TOOL_DECISIONS = {"DENY", "ERROR", "CANCELLED"}


def _require_admin(principal: Principal) -> None:
    if principal.role not in _CONTROL_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only an administrator can use the global kill switch.",
        )


# ==============================================================================
# KILL SWITCH
# ==============================================================================


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    """
    Cancel a live run: the model call or tool in progress is interrupted.
    """
    live = run_registry.get(run_id)

    if live is None or live.workspace_id != principal.workspace_id:
        raise HTTPException(
            status_code=404,
            detail="No live run with this id in your workspace.",
        )

    if live.principal_id != principal.id and principal.role not in _CONTROL_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only the run owner or an administrator can cancel it.",
        )

    run_registry.cancel(run_id, reason=f"Cancelled by {principal.id}.")

    return {"run_id": run_id, "status": "cancelling"}


@router.post("/stop-all")
async def stop_all_runs(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    _require_admin(principal)

    cancelled = run_registry.stop_all(
        reason=f"Stopped by the global kill switch ({principal.id})."
    )

    return {"halted": True, "cancelled_runs": cancelled}


@router.post("/resume")
async def resume_runs(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    _require_admin(principal)

    run_registry.resume()

    return {"halted": False}


@router.get("/live")
async def live_runs(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return {
        "halted": run_registry.halted,
        "halt_reason": run_registry.halt_reason,
        "runs": [
            {
                "run_id": live.run_id,
                "session_id": live.session_id,
                "principal_id": live.principal_id,
                "started_at": live.started_at.isoformat(),
                "cancelling": bool(getattr(live.token, "is_cancelled", False)),
            }
            for live in run_registry.active(principal.workspace_id)
        ],
    }


# ==============================================================================
# DASHBOARD
# ==============================================================================


def _workspace_runs(workspace_id: str, since: datetime) -> List[Dict[str, Any]]:
    """
    Run snapshots of a workspace created since a date.
    """
    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    runs: List[Dict[str, Any]] = []

    with SessionLocal() as db:
        rows = (
            db.query(DbAgentRun)
            .filter(DbAgentRun.created_at >= since)
            .order_by(DbAgentRun.created_at.desc())
            .all()
        )

        for row in rows:
            try:
                snapshot = json.loads(row.input_data)
            except (TypeError, ValueError):
                continue

            if snapshot.get("workspace_id") != workspace_id:
                continue

            runs.append(
                {
                    "run_id": row.id,
                    "session_id": row.session_id,
                    "status": str(row.status).lower(),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "usage": snapshot.get("usage") or {},
                }
            )

    return runs


def _failed_tool_calls(workspace_id: str, since: datetime) -> Dict[str, Any]:
    from app.core.db import SessionLocal
    from app.domain.models.audit import AuditLog

    by_tool: Dict[str, int] = defaultdict(int)

    with SessionLocal() as db:
        rows = (
            db.query(AuditLog.tool_name, AuditLog.decision)
            .filter(
                AuditLog.workspace_id == workspace_id,
                AuditLog.timestamp >= since,
            )
            .all()
        )

    for tool_name, decision in rows:
        if decision in _FAILED_TOOL_DECISIONS:
            by_tool[tool_name] += 1

    return {"total": sum(by_tool.values()), "by_tool": dict(by_tool)}


def build_stats(principal: Principal, days: int) -> Dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=days)
    runs = _workspace_runs(principal.workspace_id, since)

    inferences: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cost_by_session: Dict[str, float] = defaultdict(float)
    cost_by_role: Dict[str, float] = defaultdict(float)
    cost_by_model: Dict[str, float] = defaultdict(float)
    estimated = False

    for run in runs:
        usage = run["usage"]
        cost_by_session[run["session_id"]] += float(usage.get("cost") or 0.0)
        estimated = estimated or bool(usage.get("cost_estimated"))

        for call in usage.get("calls") or []:
            day = str(call.get("at", ""))[:10]
            model = str(call.get("model") or "unknown")
            inferences[day][model] += 1
            cost_by_role[str(call.get("role") or "unknown")] += float(call.get("cost") or 0.0)
            cost_by_model[model] += float(call.get("cost") or 0.0)

    limits = RunLimits.from_env()

    try:
        month_spent = SpendLedger.spent(principal.id, current_period())
    except Exception:
        month_spent = None

    return {
        "days": days,
        "inferences_per_day": {
            day: dict(models) for day, models in sorted(inferences.items())
        },
        "cost_by_session": {
            session: round(cost, 6) for session, cost in cost_by_session.items()
        },
        "cost_by_role": {
            role: round(cost, 6) for role, cost in cost_by_role.items()
        },
        "cost_by_model": {
            model: round(cost, 6) for model, cost in cost_by_model.items()
        },
        "runs": [
            {
                "run_id": run["run_id"],
                "session_id": run["session_id"],
                "status": run["status"],
                "created_at": run["created_at"],
                "model_calls": int(run["usage"].get("model_calls") or 0),
                "tool_calls": int(run["usage"].get("tool_calls") or 0),
                "total_tokens": int(run["usage"].get("total_tokens") or 0),
                "cost": round(float(run["usage"].get("cost") or 0.0), 6),
            }
            for run in runs[:50]
        ],
        "failed_tool_calls": _failed_tool_calls(principal.workspace_id, since),
        "cost_estimated": estimated,
        "budget": {
            "period": current_period(),
            "month_spent": month_spent,
            "monthly_budget": limits.monthly_budget,
            "max_run_cost": limits.max_run_cost,
        },
    }


@router.get("/stats")
async def run_stats(
    days: int = Query(default=30, ge=1, le=366),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return build_stats(principal, days)
