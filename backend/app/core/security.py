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

class Principal(BaseModel):
    id: str
    role: Role
    workspace_id: str

class PolicyDecision(BaseModel):
    allowed: bool
    reason: str

# ==============================================================================
# IDENTITY RESOLUTION & BINDING
# ==============================================================================
def resolve_principal(request: Request, x_session_id: str = Header(default="default-session")) -> Principal:
    """
    Cryptographically binds a session to an identity.
    In Phase 1, we map the robust SHA256 session to a Principal.
    Future phases will extract this from a JWT payload.
    """
    auth_token = request.cookies.get("aehub_auth_token", "unauth")
    
    # Block default credentials entirely
    if auth_token == "unauth" or auth_token == "default-unsafe-key":
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid identity token.")
        
    secure_id = hashlib.sha256(f"{auth_token}:{x_session_id}".encode()).hexdigest()
    
    # For Phase 1, we assume anyone with a valid auth_token matching the system secret is an ADMIN
    # Background tasks get SYSTEM. 
    from app.core.config import settings
    role = Role.ADMIN if auth_token == settings.AEHUB_SECRET_KEY else Role.USER
    
    return Principal(id=secure_id, role=role, workspace_id="default-workspace")

def get_secure_session_id(request: Request, x_session_id: str = Header(default="default-session")) -> str:
    principal = resolve_principal(request, x_session_id)
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
