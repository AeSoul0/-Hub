"""
@file backend/app/agent_engine/approval/manager.py
@description Implements manager.py. Core components: ApprovalManager.

This module manages the internal business logic for ApprovalManager.
It provides specialized functionality to handle: check_approval_status, request_approval, grant_approval.
"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.core.db import SessionLocal
from app.domain.models.audit import ApprovalRecord

class ApprovalManager:
    """
    Represents the ApprovalManager entity and its core operations.
    """
    @classmethod
    async def check_approval_status(cls, session_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Executes check_approval_status logic.
        """
        args_hash = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
        
        with SessionLocal() as db:
            record = db.query(ApprovalRecord).filter(
                ApprovalRecord.session_id == session_id,
                ApprovalRecord.tool == tool_name,
                ApprovalRecord.arguments_hash == args_hash
            ).order_by(ApprovalRecord.requested_at.desc()).first()
            
            if not record:
                return "NONE"
            
            if record.expires_at < datetime.utcnow():
                return "EXPIRED"
                
            if record.decision == "ALLOW": return "APPROVED"
            if record.decision == "DENY": return "DENIED"
            return "WAITING_APPROVAL"

    @classmethod
    async def request_approval(cls, session_id: str, tool_name: str, arguments: Dict[str, Any], principal_id: str = "system", risk: str = "low", run_id: str = None) -> str:
        """
        Executes request_approval logic.
        """
        args_hash = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
        
        with SessionLocal() as db:
            record = ApprovalRecord(
                session_id=session_id,
                tool=tool_name,
                arguments_hash=args_hash,
                requested_by=principal_id,
                risk=risk,
                run_id=run_id,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        
    @classmethod
    async def grant_approval(cls, req_id: str, decision: str, decided_by: str = "admin"):
        """
        Executes grant_approval logic.
        """
        with SessionLocal() as db:
            record = db.query(ApprovalRecord).filter(ApprovalRecord.id == req_id).first()
            if record:
                record.decision = decision
                record.decided_by = decided_by
                record.decided_at = datetime.utcnow()
                db.commit()
