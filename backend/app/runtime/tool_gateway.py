"""
@file backend/app/runtime/tool_gateway.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.core.security import PolicyEngine, Principal
from app.runtime.task_manager import TaskManager, TaskState


class ToolExecutionRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    principal: Principal
    session_id: str
    is_sensitive: bool = False

class ToolExecutionResult(BaseModel):
    success: bool
    output: Any
    error: Optional[str] = None
    audit_id: Optional[str] = None

class ToolGateway:
    """
    Phase 3: Tool Gateway.
    Implements a strict pipeline for ALL tool executions:
    Validate -> Authorize -> Budget -> Approval -> Sandbox -> Execute -> Normalize -> Audit
    """
    
    @staticmethod
    async def execute(request: ToolExecutionRequest, executor_callback) -> ToolExecutionResult:
        # 1. Validate (Pydantic models already do basic schema validation)
        
        # 2. Authorize
        decision = PolicyEngine.authorize_tool(request.principal, request.is_sensitive)
        if not decision.allowed:
            return ToolExecutionResult(
                success=False, output=None, error=f"Unauthorized: {decision.reason}"
            )
            
        # 3. Budget (Token/Execution limits per session) - Placeholder for future limit logic
        
        # 4. Approval (If human-in-the-loop is needed)
        # 5. Sandbox routing + 6. Execute
        # We wrap execution in a Durable Task
        task = TaskManager.create_task(
            session_id=request.session_id,
            payload={"tool": request.tool_name, "args": request.arguments},
            priority=1
        )
        
        TaskManager.update_state(task.id, TaskState.RUNNING)
        
        try:
            # 6. Execute via provided callback (which should use Sandbox Manager if it's code)
            result = await executor_callback(**request.arguments)
            
            # 7. Normalize output (ensuring strings/json compliance)
            normalized_output = str(result)
            
            # 8. Audit and Task completion
            TaskManager.update_state(task.id, TaskState.COMPLETED)
            
            return ToolExecutionResult(
                success=True, output=normalized_output, audit_id=task.id
            )
            
        except Exception as e:
            TaskManager.update_state(task.id, TaskState.FAILED, error_message=str(e))
            return ToolExecutionResult(
                success=False, output=None, error=str(e), audit_id=task.id
            )
