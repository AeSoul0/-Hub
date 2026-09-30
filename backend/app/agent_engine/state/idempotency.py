"""
@file backend/app/agent_engine/state/idempotency.py
@description Durable idempotency state management for tool executions.

This module stores idempotency results in PostgreSQL and provides deterministic
cache lookup semantics for the Tool Gateway.

Security and reliability invariants:
- Idempotency keys must be non-empty.
- Results are serialized as JSON whenever possible.
- Expired records are removed before returning a cache miss.
- Cache lookup never executes the underlying tool.
- Result persistence happens only after successful execution.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from app.core.db import SessionLocal
from app.domain.models.runtime_state import IdempotencyKey


DEFAULT_TTL = timedelta(days=7)


class IdempotencyManager:
    """
    Manage durable tool-execution idempotency records.
    """

    @classmethod
    def save_result(
        cls,
        idem_key: str,
        result: Any,
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        """
        Persist an execution result for a non-empty idempotency key.
        """
        cls._validate_key(idem_key)

        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be greater than zero")

        serialized = json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

        expires_at = datetime.utcnow() + ttl

        with SessionLocal() as db:
            record = (
                db.query(IdempotencyKey)
                .filter(IdempotencyKey.key == idem_key)
                .first()
            )

            if record is None:
                record = IdempotencyKey(
                    key=idem_key,
                    result=serialized,
                    expires_at=expires_at,
                )
                db.add(record)
            else:
                record.result = serialized
                record.expires_at = expires_at

            db.commit()

    @classmethod
    def get_result(
        cls,
        idem_key: str,
    ) -> Optional[Any]:
        """
        Return a cached result or None when the key is absent or expired.
        """
        cls._validate_key(idem_key)

        with SessionLocal() as db:
            record = (
                db.query(IdempotencyKey)
                .filter(IdempotencyKey.key == idem_key)
                .first()
            )

            if record is None:
                return None

            if record.expires_at <= datetime.utcnow():
                db.delete(record)
                db.commit()
                return None

            try:
                return json.loads(record.result)
            except (TypeError, json.JSONDecodeError):
                # Corrupt cache entries are never treated as valid results.
                db.delete(record)
                db.commit()
                return None

    @classmethod
    def delete(cls, idem_key: str) -> None:
        """
        Delete one durable idempotency record.
        """
        cls._validate_key(idem_key)

        with SessionLocal() as db:
            (
                db.query(IdempotencyKey)
                .filter(IdempotencyKey.key == idem_key)
                .delete(synchronize_session=False)
            )
            db.commit()

    @staticmethod
    def _validate_key(idem_key: str) -> None:
        """
        Reject empty or whitespace-only idempotency keys.
        """
        if not idem_key or not idem_key.strip():
            raise ValueError("idem_key is required")


__all__ = [
    "IdempotencyManager",
    "DEFAULT_TTL",
]