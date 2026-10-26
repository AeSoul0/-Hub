"""
@file backend/app/api/runs.py
@description Run control and spend dashboard API (roadmap M4).

POST /api/runs/{run_id}/cancel   cancel one live run (owner or admin)
POST /api/runs/stop-all          kill switch: cancel every live run and
                                 refuse new ones until resumed (admin)
POST /api/runs/resume            lift the kill switch (admin)
GET  /api/runs/live              live runs of the workspace with their totals,
                                 the per-run limits and the kill switch state
GET  /api/runs                   run history with filters (F2)
GET  /api/runs/stats             spend dashboard of the workspace
GET  /api/runs/{run_id}          one run: task, steps, observations, audit
GET  /api/runs/{run_id}/events   the run timeline from the flight recorder (F2)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent_engine.control import (
    RunLimits,
    SpendLedger,
    current_period,
    run_registry,
    usage_view,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.models import AgentRunStatus
from app.core.security import Principal, RoleEnum, resolve_principal


router = APIRouter(
    prefix="/api/runs",
    tags=["runs"],
)

_CONTROL_ROLES = {RoleEnum.ADMIN, RoleEnum.SYSTEM}
_FAILED_TOOL_DECISIONS = {"DENY", "ERROR", "CANCELLED"}
RUN_STATUSES = {status.value for status in AgentRunStatus}

# The history and the live view show the start of the task, not all of it.
TASK_PREVIEW_CHARS = 200
# A timeline longer than this keeps its most recent events.
TIMELINE_LIMIT = 500


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


def limits_view(limits: RunLimits) -> Dict[str, Any]:
    """
    The per-run limits, next to which the interface shows a run's totals.
    A limit of 0 is disabled.
    """
    return {
        "max_run_cost": limits.max_run_cost,
        "max_run_seconds": limits.max_run_seconds,
        "max_failed_tool_calls": limits.max_failed_tool_calls,
        "max_files_modified": limits.max_files_modified,
        "monthly_budget": limits.monthly_budget,
    }


def _snapshot(row: Any) -> Optional[Dict[str, Any]]:
    try:
        snapshot = json.loads(row.input_data)
    except (TypeError, ValueError):
        return None

    return snapshot if isinstance(snapshot, dict) else None


def _task_of(snapshot: Dict[str, Any]) -> Optional[str]:
    state = snapshot.get("current_state") or {}
    task = (state.get("worker_context") or {}).get("task")

    # The engine keeps the task as {"description": ...}.
    if isinstance(task, dict):
        task = task.get("description")

    if not isinstance(task, str):
        return None

    if len(task) <= TASK_PREVIEW_CHARS:
        return task

    return task[:TASK_PREVIEW_CHARS] + "…"


def _live_snapshots(run_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    The saved state of the live runs, for their totals and task. Missing
    when the database is unreachable: the live view still lists the runs.
    """
    if not run_ids:
        return {}

    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    try:
        with SessionLocal() as db:
            rows = db.query(DbAgentRun).filter(DbAgentRun.id.in_(run_ids)).all()
            found = [(row, _snapshot(row)) for row in rows]
    except Exception:
        return {}

    return {
        row.id: {**snapshot, "role": row.role, "status": str(row.status).lower()}
        for row, snapshot in found
        if snapshot is not None
    }


def live_view(principal: Principal) -> Dict[str, Any]:
    from app.agent_engine.runtime import live_usage

    active = run_registry.active(principal.workspace_id)
    snapshots = _live_snapshots([live.run_id for live in active])
    runs = []

    for live in active:
        snapshot = snapshots.get(live.run_id) or {}

        runs.append(
            {
                "run_id": live.run_id,
                "parent_run_id": snapshot.get("parent_run_id"),
                "session_id": live.session_id,
                "principal_id": live.principal_id,
                "role": snapshot.get("role"),
                "status": snapshot.get("status"),
                "task": _task_of(snapshot),
                "started_at": live.started_at.isoformat(),
                "cancelling": bool(getattr(live.token, "is_cancelled", False)),
                "usage": live_usage(live.run_id, snapshot.get("usage") or {}),
            }
        )

    return {
        "halted": run_registry.halted,
        "halt_reason": run_registry.halt_reason,
        "limits": limits_view(RunLimits.from_env()),
        "runs": runs,
    }


@router.get("/live")
async def live_runs(
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return live_view(principal)


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


# ==============================================================================
# HISTORY
# ==============================================================================


def run_history(
    principal: Principal,
    days: int = 30,
    status: Optional[str] = None,
    query: Optional[str] = None,
    subagents: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Runs of the workspace, newest first, filtered by status (comma
    separated) and text in the task or the run id; without `subagents`,
    only the runs the user started.
    """
    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    statuses = {
        item.strip().lower()
        for item in (status or "").split(",")
        if item.strip()
    }
    unknown = statuses - RUN_STATUSES

    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown run status: {', '.join(sorted(unknown))}.",
        )

    needle = (query or "").strip().lower()
    since = datetime.utcnow() - timedelta(days=days)
    matches: List[Dict[str, Any]] = []

    with SessionLocal() as db:
        rows = (
            db.query(DbAgentRun)
            .filter(DbAgentRun.created_at >= since)
            .order_by(DbAgentRun.created_at.desc())
            .all()
        )

        for row in rows:
            snapshot = _snapshot(row)

            if snapshot is None or snapshot.get("workspace_id") != principal.workspace_id:
                continue

            row_status = str(row.status).lower()

            if statuses and row_status not in statuses:
                continue

            if not subagents and snapshot.get("parent_run_id"):
                continue

            task = _task_of(snapshot)

            if needle and needle not in row.id.lower() and needle not in (task or "").lower():
                continue

            usage = snapshot.get("usage") or {}

            matches.append(
                {
                    "run_id": row.id,
                    "parent_run_id": snapshot.get("parent_run_id"),
                    "session_id": row.session_id,
                    "role": row.role,
                    "status": row_status,
                    "task": task,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "error": row.error,
                    "usage": usage_view(usage, float(usage.get("active_seconds") or 0.0)),
                }
            )

    return {
        "total": len(matches),
        "limit": limit,
        "offset": offset,
        "runs": matches[offset:offset + limit],
    }


@router.get("")
async def list_runs(
    days: int = Query(default=30, ge=1, le=366),
    status: Optional[str] = Query(default=None, max_length=200),
    q: Optional[str] = Query(default=None, max_length=200),
    subagents: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    return run_history(principal, days, status, q, subagents, limit, offset)


# ==============================================================================
# SINGLE RUN
# ==============================================================================

# Observation contents can be whole web pages; the run view shows a preview.
OBSERVATION_PREVIEW_CHARS = 1000


def _preview(text: Any, limit: int = OBSERVATION_PREVIEW_CHARS) -> str:
    text = text if isinstance(text, str) else json.dumps(text, default=str)

    if len(text) <= limit:
        return text

    return text[:limit] + "…"


def run_detail(run_id: str, workspace_id: str) -> Dict[str, Any] | None:
    """
    Everything the Control Plane shows about one run of a workspace, or
    None when the run does not exist there.
    """
    from app.api.audit import audit_entry
    from app.core.db import SessionLocal
    from app.domain.models.audit import AuditLog
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    with SessionLocal() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).first()

        if row is None:
            return None

        try:
            snapshot = json.loads(row.input_data)
        except (TypeError, ValueError):
            return None

        # A run of another workspace does not exist for this caller.
        if snapshot.get("workspace_id") != workspace_id:
            return None

        audit_rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.run_id == run_id,
                AuditLog.workspace_id == workspace_id,
            )
            .order_by(AuditLog.timestamp.asc())
            .all()
        )
        audit = [audit_entry(audit_row) for audit_row in audit_rows]

        try:
            result = json.loads(row.result) if row.result is not None else None
        except (TypeError, ValueError):
            result = row.result

        state = snapshot.get("current_state") or {}
        context = state.get("worker_context") or {}

        return {
            "run_id": row.id,
            "parent_run_id": snapshot.get("parent_run_id"),
            "session_id": row.session_id,
            "principal_id": row.principal_id,
            "role": row.role,
            "status": str(row.status).lower(),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "task": context.get("task"),
            "attempts": snapshot.get("task_attempts", 0),
            "turn": state.get("turn"),
            "result": result,
            "error": row.error,
            "errors": snapshot.get("errors") or [],
            "usage": snapshot.get("usage") or {},
            "untrusted_context": bool(context.get("untrusted_context")),
            # The tools the skill index picked for the run; None: all (F5).
            "exposed_tools": context.get("exposed_tools"),
            "pending_tool_call": context.get("pending_tool_call"),
            "queued_tool_calls": context.get("queued_tool_calls") or [],
            "last_feedback": state.get("last_feedback"),
            "observations": [
                {
                    "tool_call_id": observation.get("tool_call_id"),
                    "tool_name": observation.get("tool_name"),
                    "arguments": observation.get("arguments") or {},
                    "trusted": bool(observation.get("trusted")),
                    "succeeded": observation.get("succeeded", True),
                    "modified_file": observation.get("modified_file"),
                    "content": _preview(observation.get("content", "")),
                }
                for observation in context.get("observations") or []
                if isinstance(observation, dict)
            ],
            "audit": audit,
        }


def run_timeline(run_id: str, workspace_id: str) -> Dict[str, Any] | None:
    """
    The recorded events of one run of a workspace and the announcements of
    its subagents, oldest first; None when the run does not exist there.
    """
    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    with SessionLocal() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == run_id).first()
        snapshot = _snapshot(row) if row is not None else None

    # A run of another workspace does not exist for this caller.
    if snapshot is None or snapshot.get("workspace_id") != workspace_id:
        return None

    events = [
        event.model_dump()
        for event in EventDispatcher().get_events_for_run(run_id, include_children=True)
        if event.workspace_id == workspace_id
    ]

    return {
        "run_id": run_id,
        "truncated": len(events) > TIMELINE_LIMIT,
        "events": events[-TIMELINE_LIMIT:],
        "limits": limits_view(RunLimits.from_env()),
    }


@router.get("/{run_id}/events")
async def get_run_timeline(
    run_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    timeline = run_timeline(run_id, principal.workspace_id)

    if timeline is None:
        raise HTTPException(
            status_code=404,
            detail="No run with this id in your workspace.",
        )

    return timeline


# Registered after /live and /stats so those paths are not read as run ids.
@router.get("/{run_id}")
async def get_run(
    run_id: str,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    detail = run_detail(run_id, principal.workspace_id)

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="No run with this id in your workspace.",
        )

    return detail
