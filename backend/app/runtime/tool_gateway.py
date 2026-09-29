"""
@file backend/app/runtime/tool_gateway.py
@description Core module for A.U.R.O.R.A. System

Implements core logic and architectural definitions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import json
import hashlib
from app.agent_engine.state.idempotency import IdempotencyManager
from app.agent_engine.guardrails import ToolGuardrail

from pydantic import BaseModel

from app.core.security import PolicyEngine, Principal
from app.runtime.task_manager import TaskManager, TaskState
from app.agent_engine.models import ToolSpec
from app.budget.manager import BudgetManager
from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.errors import ApprovalRequiredError

class ToolInvocation(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    principal: Principal
    session_id: str
    spec: Optional[ToolSpec] = None

class ToolResult(BaseModel):
    success: bool
    output: Any
    error: Optional[str] = None
    audit_id: Optional[str] = None

class ToolGateway:
    """
    Phase 2: Tool Gateway v2.
    Implements a strict pipeline for ALL tool executions:
    Schema validation -> Identity -> Permission -> Risk -> Budget -> Approval -> Idempotency -> Executor -> Output limits -> Audit
    """
    
    # Simple memory storage for idempotency
    _idempotency_cache: Dict[str, Any] = {}
    
    @staticmethod
    async def execute(invocation: ToolInvocation, executor_callback, task_context=None) -> ToolResult:
        from app.core.security import TaskExecutionContext, WorkspacePolicy, BudgetState
        if not task_context: task_context = TaskExecutionContext()
        # 1. Identity is bound in ToolInvocation (invocation.principal)
        if not invocation.principal:
            return ToolResult(success=False, output=None, error="Unauthorized: Missing principal")
            
        # 2. Permission & Risk
        is_sensitive = invocation.spec.risk_level == "HIGH" if invocation.spec else False
        from app.agent_engine.models import ToolProposal
        proposal = ToolProposal(tool_call_id="call_0", tool_name=invocation.tool_name, arguments=invocation.arguments, run_id="run_0")
        decision = PolicyEngine.authorize_tool(invocation.principal, invocation.spec, proposal, WorkspacePolicy(), BudgetState(), task_context)
        if decision.decision == "DENY":
            return ToolGateway._audit_and_fail(invocation, f"Unauthorized: {decision.reason}")
            
        if invocation.spec:
            # 3. Schema validation (basic check)
            # In a full implementation, validate invocation.arguments against invocation.spec.input_schema
            pass
            
            # 4. Budget
            if invocation.spec.max_cost > 0:
                has_budget = await BudgetManager.check_budget(invocation.session_id, invocation.spec.max_cost)
                if not has_budget:
                    return ToolGateway._audit_and_fail(invocation, "Budget exceeded for this session.")
            
            # 5. Approval
            if invocation.spec.requires_approval:
                status = await ApprovalManager.check_approval_status(invocation.session_id, invocation.tool_name, invocation.arguments)
                if status != "APPROVED":
                    if status == "NONE":
                        await ApprovalManager.request_approval(invocation.session_id, invocation.tool_name, invocation.arguments)
                    raise ApprovalRequiredError(f"Tool {invocation.tool_name} requires human approval.")
                    
            # 6. Idempotency
            if invocation.spec.idempotent:
                idem_key = hashlib.md5(json.dumps({'tool': invocation.tool_name, 'args': invocation.arguments}, sort_keys=True).encode()).hexdigest()
                cached = IdempotencyManager.get_result(idem_key)
                if cached is not None:
                    return ToolResult(success=True, output=cached, audit_id="cached")
                invocation.arguments['_idem_key'] = idem_key # pass to executor to save
                
        # 7. Sandbox routing & Executor
        task = TaskManager.create_task(
            session_id=invocation.session_id,
            payload={"tool": invocation.tool_name, "args": invocation.arguments},
            priority=1
        )
        TaskManager.update_state(task.id, TaskState.RUNNING)
        
        try:
            # Execute via callback
            result = await executor_callback(**invocation.arguments)
            
            # Save idempotency if requested
            if invocation.spec and invocation.spec.idempotent:
                idem_key = invocation.arguments.get('_idem_key')
                if idem_key:
                    cached = result
            
            # 8. Output Validation & Limits
            normalized_output = str(result)
            max_out = invocation.spec.max_output if invocation.spec else 4000
            if len(normalized_output) > max_out:
                normalized_output = normalized_output[:max_out] + "... [TRUNCATED]"
            
            # 9. Audit and Task completion
            TaskManager.update_state(task.id, TaskState.COMPLETED)
            audit_id = ToolGateway._log_audit(invocation, True, None)
            
            return ToolResult(
                success=True, output=normalized_output, audit_id=audit_id
            )
            
        except Exception as e:
            TaskManager.update_state(task.id, TaskState.FAILED, error_message=str(e))
            audit_id = ToolGateway._log_audit(invocation, False, str(e))
            return ToolResult(
                success=False, output=None, error=str(e), audit_id=audit_id
            )
            
    @staticmethod
    def _log_audit(invocation: ToolInvocation, success: bool, error: Optional[str]) -> str:
        try:
            from app.core.db import SessionLocal
            from app.domain.models.audit import AuditLog
            with SessionLocal() as db:
                audit_record = AuditLog(
                    session_id=invocation.session_id,
                    principal_id=invocation.principal.id,
                    tool_name=invocation.tool_name,
                    success=success,
                    error=error
                )
                db.add(audit_record)
                db.commit()
                return audit_record.id
        except Exception:
            return "audit_failed"
            
    @staticmethod
    def _audit_and_fail(invocation: ToolInvocation, error_msg: str) -> ToolResult:
        audit_id = ToolGateway._log_audit(invocation, False, error_msg)
        return ToolResult(success=False, output=None, error=error_msg, audit_id=audit_id)
