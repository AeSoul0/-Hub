"""
@file backend/app/api/approvals.py
@description Human-in-the-loop approval API (spec 3.4).

GET  /api/approvals             pending requests of the caller's workspace,
                                with the arguments of the parked call
POST /api/approvals/{id}        decide one request: {"decision": "allow"|"deny"}

The decider is the authenticated Principal and must belong to the same
workspace as the request. A decided request cannot be decided again, and a
request left undecided past its TTL is denied by timeout.

After a decision the parked run is resumed in the background under the
identity of the run owner (loaded from durable state, never from the
request), so the ToolGateway re-checks the approval for the exact call.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Literal, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent_engine.approval.manager import (
    ApprovalClosedError,
    ApprovalManager,
)
from app.agent_engine.application import get_agent_engine
from app.agent_engine.state.manager import AgentStateManager
from app.core.event_bus import event_bus
from app.core.security import Principal, RoleEnum, resolve_principal


router = APIRouter(
    prefix="/api/approvals",
    tags=["approvals"],
)

# Strong references keep background resumes alive until they finish.
_resume_tasks: Set[asyncio.Task] = set()


class ApprovalDecision(BaseModel):
    """
    Body of a decision request.
    """

    decision: Literal["allow", "deny", "ALLOW", "DENY"]


# ==============================================================================
# BACKGROUND RESUME
# ==============================================================================


async def resume_after_decision(
    approval: Dict[str, Any],
) -> None:
    """
    Resume the run parked on this approval and publish the outcome.

    Failures are reported on the session's event stream; they never
    propagate into the HTTP request that recorded the decision.
    """
    session_id = approval["session_id"]
    run_id = approval["run_id"]

    try:
        run = AgentStateManager.load_agent_run(
            run_id,
            session_id=session_id,
            workspace_id=approval["workspace_id"],
            principal_id=approval["requested_by"],
        )

        if run is None:
            raise LookupError(f"Run {run_id} does not exist.")

        owner = Principal(
            id=approval["requested_by"],
            role=RoleEnum(run.role),
            workspace_id=approval["workspace_id"],
        )

        engine = await get_agent_engine()

        result = await engine.resume(
            run_id=run_id,
            session_id=session_id,
            principal=owner,
        )

        payload: Dict[str, Any] = {
            "run_id": run_id,
            "result": result,
        }

    except Exception as exc:
        payload = {
            "run_id": run_id,
            "error": f"Resume failed: {exc}",
        }

    try:
        await event_bus.publish(
            session_id,
            "run.resumed",
            payload,
            workspace_id=approval["workspace_id"],
        )
    except Exception:
        pass


def _schedule_resume(
    approval: Dict[str, Any],
) -> None:
    task = asyncio.create_task(
        resume_after_decision(approval)
    )
    _resume_tasks.add(task)
    task.add_done_callback(_resume_tasks.discard)


# ==============================================================================
# ROUTES
# ==============================================================================


def _parked_arguments(
    approval: Dict[str, Any],
) -> Dict[str, Any] | None:
    """
    Arguments of the call parked on this approval, read from the run's
    durable state.

    The request itself stores only their hash. They are returned only when
    the run is in the same workspace, is parked on this very approval and
    the arguments still hash to what was approved: the user decides on what
    will actually run.
    """
    from app.core.db import SessionLocal
    from app.domain.models.runtime_state import AgentRun as DbAgentRun

    if not approval.get("run_id"):
        return None

    with SessionLocal() as db:
        row = (
            db.query(DbAgentRun)
            .filter(DbAgentRun.id == approval["run_id"])
            .first()
        )

    if row is None:
        return None

    try:
        snapshot = json.loads(row.input_data)
    except (TypeError, ValueError):
        return None

    if snapshot.get("workspace_id") != approval.get("workspace_id"):
        return None

    pending = (
        (snapshot.get("current_state") or {})
        .get("worker_context", {})
        .get("pending_tool_call")
    ) or {}

    arguments = pending.get("arguments")

    if (
        pending.get("approval_id") != approval["id"]
        or not isinstance(arguments, dict)
        or ApprovalManager.argument_hash(arguments) != approval.get("arguments_hash")
    ):
        return None

    return arguments


@router.get("")
async def list_pending_approvals(
    principal: Principal = Depends(resolve_principal),
) -> List[Dict[str, Any]]:
    """
    Return the pending approval requests of the caller's workspace.
    """
    pending = await ApprovalManager.list_pending(
        principal.workspace_id
    )

    for approval in pending:
        approval.setdefault("workspace_id", principal.workspace_id)

        try:
            approval["arguments"] = _parked_arguments(approval)
        except Exception:
            approval["arguments"] = None

    return pending


@router.post("/{approval_id}")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    """
    Record an allow/deny decision and resume the parked run.
    """
    try:
        approval = await ApprovalManager.grant_approval(
            req_id=approval_id,
            decision=body.decision,
            decided_by=principal.id,
            workspace_id=principal.workspace_id,
        )
    except ApprovalClosedError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found.",
        )

    try:
        await event_bus.publish(
            approval["session_id"],
            "approval.decided",
            {
                "approval_id": approval["id"],
                "run_id": approval["run_id"],
                "decision": approval["decision"],
            },
            workspace_id=approval["workspace_id"],
        )
    except Exception:
        pass

    if approval["run_id"]:
        _schedule_resume(approval)

    return approval
