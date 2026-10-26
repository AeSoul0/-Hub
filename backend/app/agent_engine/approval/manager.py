"""
@file backend/app/agent_engine/approval/manager.py
@description Durable human-approval management for tool executions.

Approval records are bound to the authenticated session, principal, workspace,
run, tool, and canonical argument hash. This prevents an approval issued for
one tenant or execution context from being reused in another context.

Approval state is fail-closed:
- Only explicit ALLOW becomes APPROVED.
- Explicit DENY becomes DENIED.
- A request left undecided past its TTL is recorded as DENY by
  "system:timeout": silence is never consent (spec 3.4).
- Missing or pending approvals never authorize execution.

Decisions are taken by an authenticated Principal of the same workspace as
the request, once: a decided request cannot be decided again.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.db import SessionLocal
from app.core.runtime_config import config_value
from app.domain.models.audit import ApprovalRecord


DEFAULT_APPROVAL_TTL = timedelta(seconds=300)


def approval_ttl() -> timedelta:
    """
    AEHUB_APPROVAL_TTL_SECONDS as set now (Control Plane, then environment),
    so a change applies to the next approval without a restart (F4).
    """
    try:
        seconds = int(config_value("AEHUB_APPROVAL_TTL_SECONDS") or 300)
    except ValueError:
        return DEFAULT_APPROVAL_TTL

    return timedelta(seconds=seconds) if seconds > 0 else DEFAULT_APPROVAL_TTL
TIMEOUT_DECIDER = "system:timeout"
_ALLOWED_DECISIONS = {"ALLOW", "DENY"}


class ApprovalClosedError(Exception):
    """
    Raised when a decision targets a request that is already decided or
    has expired (and was therefore denied by timeout).
    """


class ApprovalManager:
    """
    Persist and resolve human approval requests.
    """

    @classmethod
    async def check_approval_status(
        cls,
        session_id: str,
        workspace_id: str,
        principal_id: str,
        run_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """
        Resolve the latest approval for an exact execution context.
        """
        cls._validate_context(
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            run_id=run_id,
            tool_name=tool_name,
        )

        args_hash = cls.argument_hash(arguments)

        with SessionLocal() as db:
            record = (
                db.query(ApprovalRecord)
                .filter(
                    ApprovalRecord.session_id == session_id,
                    ApprovalRecord.workspace_id == workspace_id,
                    ApprovalRecord.requested_by == principal_id,
                    ApprovalRecord.run_id == run_id,
                    ApprovalRecord.tool == tool_name,
                    ApprovalRecord.arguments_hash == args_hash,
                )
                .order_by(
                    ApprovalRecord.requested_at.desc()
                )
                .first()
            )

            if record is None:
                return "NONE"

            if record.decision == "DENY":
                return "DENIED"

            if record.decision == "ALLOW":
                # An ALLOW authorizes only inside its execution window.
                if record.expires_at <= datetime.utcnow():
                    return "EXPIRED"

                return "APPROVED"

            if cls._expire_if_overdue(db, record):
                return "DENIED"

            return "WAITING_APPROVAL"

    @classmethod
    async def list_pending(
        cls,
        workspace_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Return the undecided, unexpired requests of one workspace.

        Overdue requests found on the way are denied by timeout first.
        """
        if not workspace_id or not workspace_id.strip():
            raise ValueError("workspace_id is required")

        with SessionLocal() as db:
            records = (
                db.query(ApprovalRecord)
                .filter(
                    ApprovalRecord.workspace_id == workspace_id,
                    ApprovalRecord.decision.is_(None),
                )
                .order_by(
                    ApprovalRecord.requested_at.asc()
                )
                .all()
            )

            return [
                cls._to_dict(record)
                for record in records
                if not cls._expire_if_overdue(db, record)
            ]

    @classmethod
    async def request_approval(
        cls,
        session_id: str,
        workspace_id: str,
        principal_id: str,
        run_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk: str = "low",
        ttl: Optional[timedelta] = None,
    ) -> str:
        """
        Create a durable approval request for one exact execution context.
        """
        cls._validate_context(
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            run_id=run_id,
            tool_name=tool_name,
        )

        if ttl is None:
            ttl = approval_ttl()

        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be greater than zero")

        args_hash = cls.argument_hash(arguments)

        with SessionLocal() as db:
            record = ApprovalRecord(
                session_id=session_id,
                workspace_id=workspace_id,
                requested_by=principal_id,
                run_id=run_id,
                tool=tool_name,
                arguments_hash=args_hash,
                risk=risk,
                expires_at=datetime.utcnow() + ttl,
            )

            db.add(record)
            db.commit()
            db.refresh(record)

            return record.id

    @classmethod
    async def grant_approval(
        cls,
        req_id: str,
        decision: str,
        decided_by: str,
        workspace_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve an existing approval request for the deciding Principal.

        Returns the decided request, or None when no request with this id
        exists in the decider's workspace (other tenants' requests are
        indistinguishable from missing ones).

        Raises ApprovalClosedError when the request was already decided or
        has expired; an expired request is recorded as a timeout DENY.
        """
        if not req_id:
            raise ValueError("req_id is required")

        normalized_decision = decision.upper().strip()

        if normalized_decision not in _ALLOWED_DECISIONS:
            raise ValueError("decision must be ALLOW or DENY")

        if not decided_by or not decided_by.strip():
            raise ValueError("decided_by is required")

        if not workspace_id or not workspace_id.strip():
            raise ValueError("workspace_id is required")

        with SessionLocal() as db:
            record = (
                db.query(ApprovalRecord)
                .filter(
                    ApprovalRecord.id == req_id,
                    ApprovalRecord.workspace_id == workspace_id,
                )
                .first()
            )

            if record is None:
                return None

            if record.decision is not None:
                raise ApprovalClosedError(
                    "Approval request was already decided."
                )

            if cls._expire_if_overdue(db, record):
                raise ApprovalClosedError(
                    "Approval request expired and was denied by timeout."
                )

            now = datetime.utcnow()

            record.decision = normalized_decision
            record.decided_by = decided_by
            record.decided_at = now

            if normalized_decision == "ALLOW":
                # Fresh window for the resumed run to execute the call.
                record.expires_at = now + approval_ttl()

            db.commit()
            db.refresh(record)

            return cls._to_dict(record)

    @staticmethod
    def _expire_if_overdue(
        db: Any,
        record: ApprovalRecord,
    ) -> bool:
        """
        Deny an undecided request whose TTL has elapsed.

        Returns True when the request is (now) denied by timeout.
        """
        if record.decision is not None:
            return False

        now = datetime.utcnow()

        if record.expires_at > now:
            return False

        record.decision = "DENY"
        record.decided_by = TIMEOUT_DECIDER
        record.decided_at = now

        db.commit()

        return True

    @staticmethod
    def _to_dict(
        record: ApprovalRecord,
    ) -> Dict[str, Any]:
        """
        Public view of an approval request (raw arguments are never stored).
        """
        return {
            "id": record.id,
            "run_id": record.run_id,
            "session_id": record.session_id,
            "workspace_id": record.workspace_id,
            "tool": record.tool,
            "risk": record.risk,
            "arguments_hash": record.arguments_hash,
            "requested_by": record.requested_by,
            "requested_at": record.requested_at,
            "expires_at": record.expires_at,
            "decision": record.decision,
            "decided_by": record.decided_by,
            "decided_at": record.decided_at,
        }

    @staticmethod
    def argument_hash(arguments: Dict[str, Any]) -> str:
        """
        Return the canonical SHA-256 hash used by approval records.
        """
        canonical = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_context(
        session_id: str,
        workspace_id: str,
        principal_id: str,
        run_id: str,
        tool_name: str,
    ) -> None:
        """
        Validate every security boundary required by an approval.
        """
        values = {
            "session_id": session_id,
            "workspace_id": workspace_id,
            "principal_id": principal_id,
            "run_id": run_id,
            "tool_name": tool_name,
        }

        for name, value in values.items():
            if not value or not str(value).strip():
                raise ValueError(f"{name} is required")


__all__ = [
    "ApprovalClosedError",
    "ApprovalManager",
    "DEFAULT_APPROVAL_TTL",
    "approval_ttl",
    "TIMEOUT_DECIDER",
]