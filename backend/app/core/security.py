"""
@file backend/app/core/security.py
@description Implements security.py. Core components: Permission, Principal, WorkspacePolicy, BudgetState, TaskExecutionContext, SubagentCapabilitySet, IdentityService, PolicyEngine.

This module manages the internal business logic for Permission, Principal, WorkspacePolicy, BudgetState, TaskExecutionContext, SubagentCapabilitySet, IdentityService, PolicyEngine.
It provides specialized functionality to handle: intersect, create_session, validate_session, invalidate_session, resolve_principal, get_secure_session_id, authorize_tool.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

from fastapi import Header, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db, SessionLocal
from app.domain.models.identity import Session as SessionModel, User, RoleEnum, Workspace
from app.agent_engine.models import PolicyDecision, PolicyDecisionEnum, ToolSpec, ToolProposal

# ==============================================================================
# IDENTITY & PRINCIPAL MODEL
# ==============================================================================
class Permission(str, Enum):
    """
    Represents the Permission entity and its core operations.
    """
    EXECUTE_SAFE_TOOL = "tool:execute:safe"
    EXECUTE_SENSITIVE_TOOL = "tool:execute:sensitive"
    READ_MEMORY = "memory:read"
    WRITE_MEMORY = "memory:write"
    INVOKE_SUBAGENT = "agent:invoke"
    NETWORK_ACCESS = "network:access"
    FILESYSTEM_ACCESS = "fs:access"

ROLE_PERMISSIONS: Dict[RoleEnum, List[Permission]] = {
    RoleEnum.SYSTEM: list(Permission),
    RoleEnum.ADMIN: list(Permission),
    RoleEnum.MEMBER: [Permission.EXECUTE_SAFE_TOOL, Permission.READ_MEMORY, Permission.WRITE_MEMORY],
    RoleEnum.USER: [Permission.EXECUTE_SAFE_TOOL, Permission.READ_MEMORY, Permission.WRITE_MEMORY, Permission.INVOKE_SUBAGENT],
    RoleEnum.GUEST: [Permission.READ_MEMORY]
}

class Principal(BaseModel):
    """
    Represents the Principal entity and its core operations.
    """
    id: str
    role: RoleEnum
    workspace_id: str

# Context objects for Policy Engine
class WorkspacePolicy(BaseModel):
    """
    Represents the WorkspacePolicy entity and its core operations.
    """
    allowed_tools: List[str] = ["*"]

class BudgetState(BaseModel):
    """
    Represents the BudgetState entity and its core operations.
    """
    remaining: float = 100.0

class TaskExecutionContext(BaseModel):
    """
    Represents the TaskExecutionContext entity and its core operations.
    """
    is_subagent: bool = False
    subagent_capabilities: Optional['SubagentCapabilitySet'] = None

class SubagentCapabilitySet(BaseModel):
    """
    Represents the SubagentCapabilitySet entity and its core operations.
    """
    allowed_tools: List[str]
    allowed_scopes: List[str]
    max_budget: float
    max_runtime: int
    workspace: str
    permissions: List[str]
    
    @staticmethod
    def intersect(parent: 'SubagentCapabilitySet', delegated: 'SubagentCapabilitySet', policy: 'WorkspacePolicy') -> 'SubagentCapabilitySet':
        """
        Executes intersect logic.
        """
        intersected_tools = set(parent.allowed_tools) & set(delegated.allowed_tools) & set(policy.allowed_tools)
        if "*" in intersected_tools: intersected_tools.remove("*")
        intersected_scopes = set(parent.allowed_scopes) & set(delegated.allowed_scopes)
        intersected_permissions = set(parent.permissions) & set(delegated.permissions)
        return SubagentCapabilitySet(
            allowed_tools=list(intersected_tools),
            allowed_scopes=list(intersected_scopes),
            max_budget=min(parent.max_budget, delegated.max_budget),
            max_runtime=min(parent.max_runtime, delegated.max_runtime),
            workspace=parent.workspace,
            permissions=list(intersected_permissions)
        )

# ==============================================================================
# IDENTITY SERVICE
# ==============================================================================
class IdentityService:
    """
    Represents the IdentityService entity and its core operations.
    """
    @classmethod
    def create_session(cls, db: DBSession, user_id: str, workspace_id: str, role: RoleEnum) -> str:
        """
        Executes create_session logic.
        """
        session_token = secrets.token_urlsafe(32)
        new_session = SessionModel(
            id=session_token,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return session_token

    @classmethod
    def validate_session(cls, db: DBSession, session_token: str) -> Optional[SessionModel]:
        """
        Executes validate_session logic.
        """
        session_record = db.query(SessionModel).filter(SessionModel.id == session_token).first()
        if not session_record:
            return None
        if session_record.expires_at < datetime.utcnow():
            db.delete(session_record)
            db.commit()
            return None
        return session_record

    @classmethod
    def invalidate_session(cls, db: DBSession, session_token: str):
        """
        Executes invalidate_session logic.
        """
        session_record = db.query(SessionModel).filter(SessionModel.id == session_token).first()
        if session_record:
            db.delete(session_record)
            db.commit()

# ==============================================================================
# IDENTITY RESOLUTION & BINDING
# ==============================================================================
def resolve_principal(request: Request, db: DBSession = Depends(get_db)) -> Principal:
    auth_token = request.cookies.get("aehub_session_token") or request.headers.get("X-Session-ID")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing session token. Principal missing = DENY.")
        
    session = IdentityService.validate_session(db, auth_token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired session.")
    
    return Principal(id=session.user_id, role=session.role, workspace_id=session.workspace_id)

def get_secure_session_id(principal: Principal = Depends(resolve_principal)) -> str:
    return principal.id

# ==============================================================================
# POLICY ENGINE
# ==============================================================================
class PolicyEngine:
    """
    Represents the PolicyEngine entity and its core operations.
    """
    @staticmethod
    def authorize_tool(
        principal: Principal,
        tool_spec: ToolSpec,
        tool_proposal: ToolProposal,
        workspace_policy: WorkspacePolicy,
        budget_state: BudgetState,
        task_context: TaskExecutionContext
    ) -> PolicyDecision:
        
        """
        Executes authorize_tool logic.
        """
        # Missing principal = DENY
        if not principal:
            return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Missing principal.")

        # Evaluate if the principal's role grants them the necessary permission
        required_permission = Permission.EXECUTE_SENSITIVE_TOOL if tool_spec.risk_level == "HIGH" else Permission.EXECUTE_SAFE_TOOL
        
        if task_context.is_subagent:
            # Subagent explicitly requires permissions in its capability set
            if not task_context.subagent_capabilities:
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Subagent lacks explicit capability set.")
            if tool_spec.name not in task_context.subagent_capabilities.allowed_tools and "*" not in task_context.subagent_capabilities.allowed_tools:
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason=f"Tool {tool_spec.name} not in subagent allowed_tools.")
            if required_permission.value not in task_context.subagent_capabilities.permissions:
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason=f"Subagent lacks permission '{required_permission.value}'.")
        else:
            if required_permission not in ROLE_PERMISSIONS.get(principal.role, []):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY, 
                    reason=f"Principal role '{principal.role.value}' lacks permission '{required_permission.value}'."
                )

        if tool_spec.name not in workspace_policy.allowed_tools and "*" not in workspace_policy.allowed_tools:
            return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason=f"Tool {tool_spec.name} denied by WorkspacePolicy.")

        if tool_spec.network_access:
            if task_context.is_subagent and Permission.NETWORK_ACCESS.value not in task_context.subagent_capabilities.permissions:
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Subagent lacks NETWORK_ACCESS permission.")
            elif not task_context.is_subagent and Permission.NETWORK_ACCESS not in ROLE_PERMISSIONS.get(principal.role, []):
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Principal lacks NETWORK_ACCESS permission.")
                
        if tool_spec.filesystem_access:
            if task_context.is_subagent and Permission.FILESYSTEM_ACCESS.value not in task_context.subagent_capabilities.permissions:
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Subagent lacks FILESYSTEM_ACCESS permission.")
            elif not task_context.is_subagent and Permission.FILESYSTEM_ACCESS not in ROLE_PERMISSIONS.get(principal.role, []):
                return PolicyDecision(decision=PolicyDecisionEnum.DENY, reason="Principal lacks FILESYSTEM_ACCESS permission.")

        if tool_spec.requires_approval:
            return PolicyDecision(decision=PolicyDecisionEnum.REQUIRE_APPROVAL, reason="Tool requires explicit approval.")

        return PolicyDecision(decision=PolicyDecisionEnum.ALLOW, reason="Permission granted by role and policies.")

TaskExecutionContext.update_forward_refs()
