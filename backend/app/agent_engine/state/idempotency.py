"""
@file backend/app/agent_engine/state/idempotency.py
@description Implements idempotency.py. Core components: IdempotencyManager.

This module manages the internal business logic for IdempotencyManager.
It provides specialized functionality to handle: save_result, get_result.
"""
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.db import SessionLocal
from app.domain.models.runtime_state import IdempotencyKey

class IdempotencyManager:
    """
    Represents the IdempotencyManager entity and its core operations.
    """
    @classmethod
    def save_result(cls, idem_key: str, result: Any):
        """
        Executes save_result logic.
        """
        with SessionLocal() as db:
            record = db.query(IdempotencyKey).filter(IdempotencyKey.key == idem_key).first()
            if not record:
                record = IdempotencyKey(
                    key=idem_key,
                    result=json.dumps(result),
                    expires_at=datetime.utcnow() + timedelta(days=7)
                )
                db.add(record)
            else:
                record.result = json.dumps(result)
            db.commit()

    @classmethod
    def get_result(cls, idem_key: str) -> Optional[Any]:
        """
        Executes get_result logic.
        """
        with SessionLocal() as db:
            record = db.query(IdempotencyKey).filter(IdempotencyKey.key == idem_key).first()
            if record:
                if record.expires_at > datetime.utcnow():
                    return json.loads(record.result)
                else:
                    db.delete(record)
                    db.commit()
        return None
