"""
@file backend/app/agent_engine/approval/manager.py
@description Durable human-approval management for tool executions.

Approval records are bound to the authenticated session, principal, workspace,
run, tool, and canonical argument hash. This prevents an approval issued for
one tenant or execution context from being reused in another context.

Approval state is fail-closed:
- Only explicit ALLOW becomes APPROVED.
- Explicit DENY becomes DENIED.
- Missing, pending, or expired approvals never authorize execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict

from app.core.db import SessionLocal
from app.domain.models.audit import ApprovalRecord


DEFAULT_APPROVAL_TTL = timedelta(hours=24)
_ALLOWED_DECISIONS = {"ALLOW", "DENY"}


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

            if record.expires_at <= datetime.utcnow():
                return "EXPIRED"

            if record.decision == "ALLOW":
                return "APPROVED"

            if record.decision == "DENY":
                return "DENIED"

            return "WAITING_APPROVAL"

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
        ttl: timedelta = DEFAULT_APPROVAL_TTL,
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
        decided_by: str = "admin",
    ) -> bool:
        """
        Resolve an existing approval request.

        Only ALLOW and DENY are accepted. Expired requests cannot be granted.
        """
        if not req_id:
            raise ValueError("req_id is required")

        normalized_decision = decision.upper().strip()

        if normalized_decision not in _ALLOWED_DECISIONS:
            raise ValueError("decision must be ALLOW or DENY")

        if not decided_by or not decided_by.strip():
            raise ValueError("decided_by is required")

        with SessionLocal() as db:
            record = (
                db.query(ApprovalRecord)
                .filter(ApprovalRecord.id == req_id)
                .first()
            )

            if record is None:
                return False

            if record.expires_at <= datetime.utcnow():
                return False

            record.decision = normalized_decision
            record.decided_by = decided_by
            record.decided_at = datetime.utcnow()

            db.commit()

            return True

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
    "ApprovalManager",
    "DEFAULT_APPROVAL_TTL",
]