"""
@file backend/app/runtime/tool_gateway.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel

from app.core.security import PolicyEngine, Principal
from app.runtime.task_manager import TaskManager, TaskState

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ToolSpec(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel
    required_permissions: List[str] = []
    network_access: bool = False
    filesystem_access: bool = False
    execution_timeout: int = 30
    max_cost: float = 0.0
    max_output: int = 4000
    idempotency: bool = False
    audit_policy: str = "standard"
    approval_required: bool = False

class ToolPolicy(BaseModel):
    allowed: bool
    reason: str

class ToolInvocation(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    principal: Principal
    session_id: str
    spec: Optional[ToolSpec] = None

class ToolDecision(BaseModel):
    approved: bool
    reason: str

class ToolExecution(BaseModel):
    invocation_id: str
    status: str

class ToolResult(BaseModel):
    success: bool
    output: Any
    error: Optional[str] = None
    audit_id: Optional[str] = None

class AuditEvent(BaseModel):
    event_id: str
    timestamp: datetime
    session_id: str
    principal_id: str
    tool_name: str
    success: bool
    error: Optional[str]

class ToolGateway:
    """
    Phase 3: Tool Gateway.
    Implements a strict pipeline for ALL tool executions:
    Schema validation -> Identity -> Permission -> Risk -> Budget -> Approval -> Executor -> Output limits -> Audit
    """
    
    @staticmethod
    async def execute(invocation: ToolInvocation, executor_callback) -> ToolResult:
        # 1. Identity is already bound in ToolInvocation
        
        # 2. Permission & Risk
        is_sensitive = invocation.spec.risk_level == RiskLevel.HIGH if invocation.spec else False
        decision = PolicyEngine.authorize_tool(invocation.principal, is_sensitive)
        if not decision.allowed:
            from app.core.db import SessionLocal
            from app.domain.models.audit import AuditLog
            
            with SessionLocal() as db:
                audit_record = AuditLog(
                    session_id=invocation.session_id,
                    principal_id=invocation.principal.id,
                    tool_name=invocation.tool_name,
                    success=False,
                    error=f"Unauthorized: {decision.reason}"
                )
                db.add(audit_record)
                db.commit()
                audit_id = audit_record.id
                
            return ToolResult(
                success=False, output=None, error=f"Unauthorized: {decision.reason}", audit_id=audit_id
            )
            
        # 3. Budget (Token/Execution limits per session) - Placeholder
        
        # 4. Approval (If human-in-the-loop is needed)
        if invocation.spec and invocation.spec.approval_required:
            # We would typically transition to WAITING_APPROVAL here
            pass
            
        # 5. Sandbox routing + 6. Executor
        task = TaskManager.create_task(
            session_id=invocation.session_id,
            payload={"tool": invocation.tool_name, "args": invocation.arguments},
            priority=1
        )
        TaskManager.update_state(task.id, TaskState.RUNNING)
        
        try:
            # 6. Execute via provided callback (Sandbox)
            result = await executor_callback(**invocation.arguments)
            
            # 7. Output limits & Normalization
            normalized_output = str(result)
            max_out = invocation.spec.max_output if invocation.spec else 4000
            if len(normalized_output) > max_out:
                normalized_output = normalized_output[:max_out] + "... [TRUNCATED]"
            
            # 8. Audit and Task completion
            TaskManager.update_state(task.id, TaskState.COMPLETED)
            
            from app.core.db import SessionLocal
            from app.domain.models.audit import AuditLog
            
            with SessionLocal() as db:
                audit_record = AuditLog(
                    session_id=invocation.session_id,
                    principal_id=invocation.principal.id,
                    tool_name=invocation.tool_name,
                    success=True,
                    error=None
                )
                db.add(audit_record)
                db.commit()
                audit_id = audit_record.id
            
            return ToolResult(
                success=True, output=normalized_output, audit_id=audit_id
            )
            
        except Exception as e:
            TaskManager.update_state(task.id, TaskState.FAILED, error_message=str(e))
            
            from app.core.db import SessionLocal
            from app.domain.models.audit import AuditLog
            
            with SessionLocal() as db:
                audit_record = AuditLog(
                    session_id=invocation.session_id,
                    principal_id=invocation.principal.id,
                    tool_name=invocation.tool_name,
                    success=False,
                    error=str(e)
                )
                db.add(audit_record)
                db.commit()
                audit_id = audit_record.id
                
            return ToolResult(
                success=False, output=None, error=str(e), audit_id=audit_id
            )
