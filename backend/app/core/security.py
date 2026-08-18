"""
@file backend/app/core/security.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Header, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db, SessionLocal
from app.domain.models.identity import Session as SessionModel, User, RoleEnum, Workspace

# ==============================================================================
# IDENTITY & PRINCIPAL MODEL
# ==============================================================================
class Permission(str, Enum):
    EXECUTE_SAFE_TOOL = "tool:execute:safe"
    EXECUTE_SENSITIVE_TOOL = "tool:execute:sensitive"
    READ_MEMORY = "memory:read"
    WRITE_MEMORY = "memory:write"
    INVOKE_SUBAGENT = "agent:invoke"

# Map roles to their permission sets
ROLE_PERMISSIONS: Dict[RoleEnum, List[Permission]] = {
    RoleEnum.SYSTEM: list(Permission),
    RoleEnum.ADMIN: list(Permission),
    RoleEnum.MEMBER: [Permission.EXECUTE_SAFE_TOOL, Permission.READ_MEMORY, Permission.WRITE_MEMORY],
    RoleEnum.USER: [Permission.EXECUTE_SAFE_TOOL, Permission.READ_MEMORY, Permission.WRITE_MEMORY, Permission.INVOKE_SUBAGENT],
    RoleEnum.GUEST: [Permission.READ_MEMORY]
}

class Principal(BaseModel):
    id: str
    role: RoleEnum
    workspace_id: str

class PolicyDecision(BaseModel):
    allowed: bool
    reason: str

# ==============================================================================
# IDENTITY SERVICE
# ==============================================================================
class IdentityService:
    """
    Handles robust session management backed by PostgreSQL (M1 Requirement).
    """

    @classmethod
    def create_session(cls, db: DBSession, user_id: str, workspace_id: str, role: RoleEnum) -> str:
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
        session_record = db.query(SessionModel).filter(SessionModel.id == session_token).first()
        if session_record:
            db.delete(session_record)
            db.commit()


# ==============================================================================
# IDENTITY RESOLUTION & BINDING
# ==============================================================================
def resolve_principal(request: Request, db: DBSession = Depends(get_db)) -> Principal:
    """
    Validates the session token from the Request headers/cookies
    and extracts the bound principal.
    M1 Requirement: Fail closed.
    """
    auth_token = request.cookies.get("aehub_session_token") or request.headers.get("X-Session-ID")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing session token. Principal missing = DENY.")
        
    session = IdentityService.validate_session(db, auth_token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired session.")
    
    return Principal(id=session.user_id, role=session.role, workspace_id=session.workspace_id)

def get_secure_session_id(principal: Principal = Depends(resolve_principal)) -> str:
    """
    Returns the user's secure session identifier for downstream isolation.
    """
    return principal.id

# ==============================================================================
# POLICY ENGINE
# ==============================================================================
class PolicyEngine:
    @staticmethod
    def authorize(principal: Principal, required_permission: Permission) -> PolicyDecision:
        if required_permission in ROLE_PERMISSIONS.get(principal.role, []):
            return PolicyDecision(allowed=True, reason="Permission granted by role.")
        return PolicyDecision(
            allowed=False, 
            reason=f"Principal role '{principal.role.value}' lacks permission '{required_permission.value}'."
        )
        
    @staticmethod
    def authorize_tool(principal: Principal, is_sensitive: bool) -> PolicyDecision:
        perm = Permission.EXECUTE_SENSITIVE_TOOL if is_sensitive else Permission.EXECUTE_SAFE_TOOL
        return PolicyEngine.authorize(principal, perm)
