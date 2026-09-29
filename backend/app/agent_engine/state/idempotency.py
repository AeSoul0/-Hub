"""
@file backend/app/agent_engine/state/idempotency.py
@description Tool Execution Idempotency Engine.

Caches tool executions based on deterministic keys. 
Ensures that if the agent runtime crashes mid-iteration, side effects 
are never repeated during recovery loops (Phase 5).
"""

import json
import os
from typing import Dict, Any, Optional

IDEMPOTENCY_FILE = "idempotency_cache.json"

class IdempotencyManager:
    @classmethod
    def save_result(cls, idem_key: str, result: Any):
        data = {}
        if os.path.exists(IDEMPOTENCY_FILE):
            with open(IDEMPOTENCY_FILE, "r") as f:
                data = json.load(f)
        data[idem_key] = result
        with open(IDEMPOTENCY_FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def get_result(cls, idem_key: str) -> Optional[Any]:
        if os.path.exists(IDEMPOTENCY_FILE):
            with open(IDEMPOTENCY_FILE, "r") as f:
                data = json.load(f)
            return data.get(idem_key)
        return None
