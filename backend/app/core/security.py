"""
@file backend/app/core/security.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import hashlib
from enum import Enum
from typing import Dict, List

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel


# ==============================================================================
# IDENTITY & PRINCIPAL MODEL
# ==============================================================================
class Role(str, Enum):
    SYSTEM = "system"       # Unrestricted background daemons
    ADMIN = "admin"         # Full capability access
    USER = "user"           # Standard operations, restricted sensitive tools
    GUEST = "guest"         # Read-only memory, no execution

class Permission(str, Enum):
    EXECUTE_SAFE_TOOL = "tool:execute:safe"
    EXECUTE_SENSITIVE_TOOL = "tool:execute:sensitive"
    READ_MEMORY = "memory:read"
    WRITE_MEMORY = "memory:write"
    INVOKE_SUBAGENT = "agent:invoke"

ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.SYSTEM: list(Permission),
    Role.ADMIN: list(Permission),
    Role.USER: [Permission.EXECUTE_SAFE_TOOL, Permission.READ_MEMORY, Permission.WRITE_MEMORY, Permission.INVOKE_SUBAGENT],
    Role.GUEST: [Permission.READ_MEMORY]
}

from datetime import datetime, timedelta
import secrets

class Workspace(BaseModel):
    id: str
    name: str

class Session(BaseModel):
    id: str
    user_id: str
    role: Role
    workspace_id: str
    expires_at: datetime

class Principal(BaseModel):
    id: str
    role: Role
    workspace_id: str

class PolicyDecision(BaseModel):
    allowed: bool
    reason: str

# ==============================================================================
# IDENTITY SERVICE
# ==============================================================================
class IdentityService:
    # In-memory session store for Phase 1. 
    # Must be moved to Redis or Postgres for durable multi-worker execution.
    _sessions: Dict[str, Session] = {}

    @classmethod
    def create_session(cls, user_id: str, role: Role, workspace_id: str = "default-workspace") -> str:
        session_token = secrets.token_urlsafe(32)
        cls._sessions[session_token] = Session(
            id=session_token,
            user_id=user_id,
            role=role,
            workspace_id=workspace_id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        return session_token

    @classmethod
    def validate_session(cls, session_token: str) -> Session:
        session = cls._sessions.get(session_token)
        if not session or session.expires_at < datetime.utcnow():
            return None
        return session

    @classmethod
    def invalidate_session(cls, session_token: str):
        cls._sessions.pop(session_token, None)


# ==============================================================================
# IDENTITY RESOLUTION & BINDING
# ==============================================================================
def resolve_principal(request: Request) -> Principal:
    """
    Validates the session token and extracts the bound principal.
    No longer uses AEHUB_SECRET_KEY as a bearer credential.
    """
    auth_token = request.cookies.get("aehub_session_token")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing session token.")
        
    session = IdentityService.validate_session(auth_token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired session.")
    
    return Principal(id=session.user_id, role=session.role, workspace_id=session.workspace_id)

def get_secure_session_id(request: Request) -> str:
    principal = resolve_principal(request)
    return principal.id

# ==============================================================================
# POLICY ENGINE
# ==============================================================================
class PolicyEngine:
    @staticmethod
    def authorize(principal: Principal, required_permission: Permission) -> PolicyDecision:
        if required_permission in ROLE_PERMISSIONS.get(principal.role, []):
            return PolicyDecision(allowed=True, reason="Permission granted by role.")
        return PolicyDecision(allowed=False, reason=f"Principal role '{principal.role.value}' lacks permission '{required_permission.value}'.")
        
    @staticmethod
    def authorize_tool(principal: Principal, is_sensitive: bool) -> PolicyDecision:
        perm = Permission.EXECUTE_SENSITIVE_TOOL if is_sensitive else Permission.EXECUTE_SAFE_TOOL
        return PolicyEngine.authorize(principal, perm)
