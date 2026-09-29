"""
@file backend/app/agent_engine/approvalmanager.py
@description Core module for A.U.R.O.R.A. System Engine.

Implements architectural specifications according to the project roadmap.
Ensures durable execution, secure boundaries, and strict multi-agent orchestration.
"""

from typing import Dict, Any, Optional
import json
import os
import uuid
from datetime import datetime, timedelta
from app.agent_engine.models import ApprovalRequest

APPROVAL_FILE = "approvals.json"

class ApprovalManager:
    @classmethod
    def _load_db(cls) -> Dict[str, Any]:
        if os.path.exists(APPROVAL_FILE):
            with open(APPROVAL_FILE, "r") as f:
                return json.load(f)
        return {}

    @classmethod
    def _save_db(cls, db: Dict[str, Any]):
        with open(APPROVAL_FILE, "w") as f:
            json.dump(db, f)

    @classmethod
    async def check_approval_status(cls, session_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        db = cls._load_db()
        key = f"{session_id}:{tool_name}:{str(arguments)}"
        for req_id, req in db.items():
            if req.get("key") == key:
                decision = req.get("decision")
                if decision == "ALLOW": return "APPROVED"
                if decision == "DENY": return "DENIED"
                return "WAITING_APPROVAL"
        return "NONE"

    @classmethod
    async def request_approval(cls, session_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        db = cls._load_db()
        req_id = str(uuid.uuid4())
        key = f"{session_id}:{tool_name}:{str(arguments)}"
        db[req_id] = {
            "id": req_id,
            "key": key,
            "session_id": session_id,
            "tool": tool_name,
            "arguments": arguments,
            "status": "WAITING_APPROVAL",
            "decision": None,
            "requested_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        cls._save_db(db)
        return req_id
        
    @classmethod
    async def grant_approval(cls, req_id: str, decision: str):
        db = cls._load_db()
        if req_id in db:
            db[req_id]["decision"] = decision
            db[req_id]["status"] = "COMPLETED"
            cls._save_db(db)
