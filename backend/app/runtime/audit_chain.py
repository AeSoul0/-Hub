"""
@file backend/app/runtime/audit_chain.py
@description Append-only, tamper-evident audit writes.

Every AuditLog row is written together with an AuditChainLink holding

    record_hash = SHA-256(prev_hash || canonical(row))

in the same transaction. Editing, deleting or reordering a row breaks the
chain from that point on, which verify_audit_chain() reports.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.domain.models.audit import AuditChainLink, AuditLog


GENESIS_HASH = "0" * 64

# Serializes writers in this process; the primary key on seq catches a
# concurrent writer in another process, which is then retried.
_CHAIN_LOCK = threading.Lock()
_MAX_APPEND_ATTEMPTS = 3

_HASHED_FIELDS = (
    "id",
    "timestamp",
    "session_id",
    "run_id",
    "tool_call_id",
    "principal_id",
    "workspace_id",
    "tool_name",
    "risk",
    "arguments_hash",
    "decision",
    "success",
    "execution_result",
    "duration",
    "error",
)


def _canonical(record: AuditLog) -> str:
    payload = {}

    for field in _HASHED_FIELDS:
        value = getattr(record, field)
        if isinstance(value, datetime):
            value = value.isoformat()
        payload[field] = value

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_record_hash(prev_hash: str, record: AuditLog) -> str:
    return hashlib.sha256(
        (prev_hash + _canonical(record)).encode("utf-8")
    ).hexdigest()


def append_audit_record(db: DBSession, **fields: Any) -> str:
    """
    Persist one AuditLog row and its chain link atomically.

    Raises on failure: callers decide whether a failed audit write blocks
    the action (the ToolGateway fails closed).
    """
    with _CHAIN_LOCK:
        for attempt in range(_MAX_APPEND_ATTEMPTS):
            record = AuditLog(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                **fields,
            )

            last = (
                db.query(AuditChainLink)
                .order_by(AuditChainLink.seq.desc())
                .first()
            )

            prev_hash = last.record_hash if last else GENESIS_HASH
            seq = (last.seq + 1) if last else 1

            db.add(record)

            try:
                # Flush first so column defaults are part of the hash.
                db.flush()
                db.add(
                    AuditChainLink(
                        seq=seq,
                        audit_id=record.id,
                        prev_hash=prev_hash,
                        record_hash=compute_record_hash(prev_hash, record),
                    )
                )
                db.commit()
            except IntegrityError:
                db.rollback()
                if attempt == _MAX_APPEND_ATTEMPTS - 1:
                    raise
                continue

            return record.id

    raise RuntimeError("Audit chain append failed.")


@dataclass
class ChainVerification:
    valid: bool
    checked: int
    broken_at_seq: Optional[int] = None
    reason: Optional[str] = None


def verify_audit_chain(db: DBSession) -> ChainVerification:
    """
    Walk the chain from the genesis link and recompute every hash.
    """
    prev_hash = GENESIS_HASH
    expected_seq = 1
    checked = 0

    links = db.query(AuditChainLink).order_by(AuditChainLink.seq.asc()).all()

    for link in links:
        if link.seq != expected_seq:
            return ChainVerification(False, checked, expected_seq, "missing link")

        if link.prev_hash != prev_hash:
            return ChainVerification(False, checked, link.seq, "prev_hash mismatch")

        record = db.query(AuditLog).filter(AuditLog.id == link.audit_id).first()

        if record is None:
            return ChainVerification(False, checked, link.seq, "audit row deleted")

        if compute_record_hash(prev_hash, record) != link.record_hash:
            return ChainVerification(False, checked, link.seq, "audit row modified")

        prev_hash = link.record_hash
        expected_seq += 1
        checked += 1

    return ChainVerification(True, checked)


__all__ = [
    "ChainVerification",
    "GENESIS_HASH",
    "append_audit_record",
    "compute_record_hash",
    "verify_audit_chain",
]
