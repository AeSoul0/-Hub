"""
@file backend/app/api/audit.py
@description Read-only audit view for the Control Plane Security page (M11).

GET /api/audit    recent tool calls of the caller's workspace, as recorded by
                  the Tool Gateway, plus a verification of the hash chain.

Nothing here writes: the audit log is append-only and only the Gateway adds
to it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, resolve_principal


router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
)

# Tool results can be long; the page shows a preview.
RESULT_PREVIEW_CHARS = 500


def _preview(text: Optional[str]) -> Optional[str]:
    if text is None or len(text) <= RESULT_PREVIEW_CHARS:
        return text

    return text[:RESULT_PREVIEW_CHARS] + "…"


def audit_entry(row: Any) -> Dict[str, Any]:
    """
    One AuditLog row as the API returns it.
    """
    return {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "session_id": row.session_id,
        "run_id": row.run_id,
        "tool_call_id": row.tool_call_id,
        "principal_id": row.principal_id,
        "tool_name": row.tool_name,
        "risk": row.risk,
        "decision": row.decision,
        "success": bool(row.success),
        "duration": row.duration,
        "error": _preview(row.error),
        "result_preview": _preview(row.execution_result),
    }


@router.get("")
async def recent_audit(
    limit: int = Query(default=100, ge=1, le=500),
    decision: Optional[str] = Query(default=None, max_length=32),
    principal: Principal = Depends(resolve_principal),
) -> Dict[str, Any]:
    """
    Latest audit entries of the workspace and the state of the hash chain.
    """
    from app.core.db import SessionLocal
    from app.domain.models.audit import AuditLog
    from app.runtime.audit_chain import verify_audit_chain

    with SessionLocal() as db:
        query = db.query(AuditLog).filter(
            AuditLog.workspace_id == principal.workspace_id,
        )

        if decision:
            query = query.filter(AuditLog.decision == decision.upper())

        rows = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
        entries = [audit_entry(row) for row in rows]

        chain = verify_audit_chain(db)

    return {
        "entries": entries,
        "chain": {
            "valid": chain.valid,
            "checked": chain.checked,
            "broken_at_seq": chain.broken_at_seq,
            "reason": chain.reason,
        },
    }
