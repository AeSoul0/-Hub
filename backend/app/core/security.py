"""
@file backend/app/core/security.py
@description Identity, RBAC, workspace isolation and policy enforcement.
"""

import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.agent_engine.models import (
    PolicyDecision,
    PolicyDecisionEnum,
    ToolProposal,
    ToolSpec,
)
from app.core.db import get_db
from app.domain.models.identity import (
    RoleEnum,
    Session as SessionModel,
    User,
    WorkspaceMembership,
)


class Permission(str, Enum):
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
    RoleEnum.MEMBER: [
        Permission.EXECUTE_SAFE_TOOL,
        Permission.READ_MEMORY,
        Permission.WRITE_MEMORY,
    ],
    RoleEnum.USER: [
        Permission.EXECUTE_SAFE_TOOL,
        Permission.READ_MEMORY,
        Permission.WRITE_MEMORY,
        Permission.INVOKE_SUBAGENT,
    ],
    RoleEnum.GUEST: [
        Permission.READ_MEMORY,
    ],
}


class Principal(BaseModel):
    id: str
    role: RoleEnum
    workspace_id: str


class WorkspacePolicy(BaseModel):
    allowed_tools: List[str] = Field(
        default_factory=lambda: ["*"]
    )
    workspace_id: Optional[str] = None


class BudgetState(BaseModel):
    remaining: float = 100.0


class TaskExecutionContext(BaseModel):
    is_subagent: bool = False
    subagent_capabilities: Optional[
        "SubagentCapabilitySet"
    ] = None
    workspace_id: Optional[str] = None


class SubagentCapabilitySet(BaseModel):
    allowed_tools: List[str]
    allowed_scopes: List[str]
    max_budget: float
    max_runtime: int
    workspace: str
    permissions: List[str]

    @staticmethod
    def intersect(
        parent: "SubagentCapabilitySet",
        delegated: "SubagentCapabilitySet",
        policy: WorkspacePolicy,
    ) -> "SubagentCapabilitySet":
        """
        Calculate the effective child capability set.

        Capabilities can only become narrower:
        parent ∩ delegated ∩ workspace policy.
        """

        if parent.workspace != delegated.workspace:
            raise ValueError(
                "Parent and delegated workspace must match."
            )

        if (
            policy.workspace_id
            and policy.workspace_id != parent.workspace
        ):
            raise ValueError(
                "Workspace policy does not match capability workspace."
            )

        def intersect_wildcards(
            left: List[str],
            right: List[str],
            policy_values: List[str],
        ) -> List[str]:
            sets = [
                set(left),
                set(right),
                set(policy_values),
            ]

            concrete_sets = [
                s for s in sets if "*" not in s
            ]

            if not concrete_sets:
                return ["*"]

            result = set(concrete_sets[0])

            for current in concrete_sets[1:]:
                result &= current

            return sorted(result)

        allowed_tools = intersect_wildcards(
            parent.allowed_tools,
            delegated.allowed_tools,
            policy.allowed_tools,
        )

        allowed_scopes = sorted(
            set(parent.allowed_scopes)
            & set(delegated.allowed_scopes)
        )

        permissions = sorted(
            set(parent.permissions)
            & set(delegated.permissions)
        )

        return SubagentCapabilitySet(
            allowed_tools=allowed_tools,
            allowed_scopes=allowed_scopes,
            max_budget=min(
                parent.max_budget,
                delegated.max_budget,
            ),
            max_runtime=min(
                parent.max_runtime,
                delegated.max_runtime,
            ),
            workspace=parent.workspace,
            permissions=permissions,
        )


# Resolve the forward reference after both models exist.
TaskExecutionContext.model_rebuild()


class IdentityService:
    """
    Persistent session lifecycle.

    A session is valid only while:
    - the session exists;
    - it is not expired;
    - the associated user is active;
    - the user still belongs to the workspace.
    """

    @classmethod
    def create_session(
        cls,
        db: DBSession,
        user_id: str,
        workspace_id: str,
        role: RoleEnum,
    ) -> str:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="Invalid or inactive user.",
            )

        membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.workspace_id == workspace_id,
            )
            .first()
        )

        if not membership:
            raise HTTPException(
                status_code=403,
                detail=(
                    "User is not a member of the requested "
                    "workspace."
                ),
            )

        if membership.role != role:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Requested role does not match "
                    "workspace membership."
                ),
            )

        session_token = secrets.token_urlsafe(32)

        session = SessionModel(
            id=session_token,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            expires_at=(
                datetime.utcnow()
                + timedelta(days=7)
            ),
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return session_token

    @classmethod
    def validate_session(
        cls,
        db: DBSession,
        session_token: str,
    ) -> Optional[SessionModel]:
        session = (
            db.query(SessionModel)
            .filter(SessionModel.id == session_token)
            .first()
        )

        if not session:
            return None

        if session.expires_at <= datetime.utcnow():
            db.delete(session)
            db.commit()
            return None

        user = (
            db.query(User)
            .filter(User.id == session.user_id)
            .first()
        )

        if not user or not user.is_active:
            return None

        membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.user_id
                == session.user_id,
                WorkspaceMembership.workspace_id
                == session.workspace_id,
            )
            .first()
        )

        if not membership:
            return None

        if membership.role != session.role:
            return None

        return session

    @classmethod
    def invalidate_session(
        cls,
        db: DBSession,
        session_token: str,
    ) -> None:
        session = (
            db.query(SessionModel)
            .filter(SessionModel.id == session_token)
            .first()
        )

        if session:
            db.delete(session)
            db.commit()


def resolve_principal(
    request: Request,
    db: DBSession = Depends(get_db),
) -> Principal:
    """
    Resolve the authenticated principal from the persisted session.

    Cookie is preferred; X-Session-ID remains supported for compatibility
    with the existing frontend/API contract.
    """

    session_token = (
        request.cookies.get(
            "aehub_session_token"
        )
        or request.headers.get("X-Session-ID")
    )

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: missing session token.",
        )

    session = IdentityService.validate_session(
        db,
        session_token,
    )

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: invalid or expired session.",
        )

    return Principal(
        id=session.user_id,
        role=session.role,
        workspace_id=session.workspace_id,
    )


def get_secure_session_id(
    principal: Principal = Depends(resolve_principal),
) -> str:
    """
    Preserve the existing API contract where callers use this dependency
    as an authenticated principal identifier.
    """

    return principal.id


class PolicyEngine:
    """
    Central authorization boundary.

    No LLM output is trusted directly. Authorization is derived from:
    - principal RBAC;
    - workspace policy;
    - delegated subagent capabilities;
    - network/filesystem permissions;
    - budget;
    - tool/proposal consistency.
    """

    @staticmethod
    def authorize_tool(
        principal: Optional[Principal],
        tool_spec: ToolSpec,
        tool_proposal: ToolProposal,
        workspace_policy: WorkspacePolicy,
        budget_state: BudgetState,
        task_context: TaskExecutionContext,
    ) -> PolicyDecision:

        if principal is None:
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason="Missing principal.",
            )

        if (
            tool_spec.name
            != tool_proposal.tool_name
        ):
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason=(
                    "Tool proposal does not match ToolSpec."
                ),
            )

        if (
            workspace_policy.workspace_id
            and principal.workspace_id
            != workspace_policy.workspace_id
        ):
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason=(
                    "Principal workspace does not match "
                    "policy workspace."
                ),
            )

        if (
            task_context.workspace_id
            and principal.workspace_id
            != task_context.workspace_id
        ):
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason=(
                    "Principal workspace does not match "
                    "execution workspace."
                ),
            )

        if (
            tool_spec.max_cost > 0
            and budget_state.remaining
            < tool_spec.max_cost
        ):
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason="Insufficient execution budget.",
            )

        allowed_tools = set(
            workspace_policy.allowed_tools
        )

        if (
            "*"
            not in allowed_tools
            and tool_spec.name not in allowed_tools
        ):
            return PolicyDecision(
                decision=PolicyDecisionEnum.DENY,
                reason=(
                    f"Tool {tool_spec.name} denied "
                    "by WorkspacePolicy."
                ),
            )

        required_permission = (
            Permission.EXECUTE_SENSITIVE_TOOL
            if tool_spec.risk_level.upper()
            == "HIGH"
            else Permission.EXECUTE_SAFE_TOOL
        )

        if task_context.is_subagent:
            capabilities = (
                task_context.subagent_capabilities
            )

            if capabilities is None:
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Subagent lacks explicit "
                        "capability set."
                    ),
                )

            if (
                capabilities.workspace
                != principal.workspace_id
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Subagent capability "
                        "workspace mismatch."
                    ),
                )

            if (
                "*"
                not in capabilities.allowed_tools
                and tool_spec.name
                not in capabilities.allowed_tools
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        f"Tool {tool_spec.name} "
                        "is not delegated."
                    ),
                )

            if (
                required_permission.value
                not in capabilities.permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Subagent lacks permission "
                        f"'{required_permission.value}'."
                    ),
                )

            for permission in tool_spec.permissions:
                if permission not in capabilities.permissions:
                    return PolicyDecision(
                        decision=PolicyDecisionEnum.DENY,
                        reason=(
                            "Subagent lacks tool "
                            f"permission '{permission}'."
                        ),
                    )

            if (
                tool_spec.network_access
                and Permission.NETWORK_ACCESS.value
                not in capabilities.permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Subagent lacks NETWORK_ACCESS "
                        "permission."
                    ),
                )

            if (
                tool_spec.filesystem_access
                and Permission.FILESYSTEM_ACCESS.value
                not in capabilities.permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Subagent lacks "
                        "FILESYSTEM_ACCESS permission."
                    ),
                )

        else:
            role_permissions = set(
                ROLE_PERMISSIONS.get(
                    principal.role,
                    [],
                )
            )

            if (
                required_permission
                not in role_permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        f"Principal role "
                        f"'{principal.role.value}' "
                        "lacks permission "
                        f"'{required_permission.value}'."
                    ),
                )

            for permission in tool_spec.permissions:
                try:
                    required = Permission(permission)
                except ValueError:
                    return PolicyDecision(
                        decision=PolicyDecisionEnum.DENY,
                        reason=(
                            f"Unknown tool permission "
                            f"'{permission}'."
                        ),
                    )

                if (
                    required
                    not in role_permissions
                ):
                    return PolicyDecision(
                        decision=PolicyDecisionEnum.DENY,
                        reason=(
                            "Principal lacks required "
                            "tool permission "
                            f"'{permission}'."
                        ),
                    )

            if (
                tool_spec.network_access
                and Permission.NETWORK_ACCESS
                not in role_permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Principal lacks "
                        "NETWORK_ACCESS permission."
                    ),
                )

            if (
                tool_spec.filesystem_access
                and Permission.FILESYSTEM_ACCESS
                not in role_permissions
            ):
                return PolicyDecision(
                    decision=PolicyDecisionEnum.DENY,
                    reason=(
                        "Principal lacks "
                        "FILESYSTEM_ACCESS permission."
                    ),
                )

        if tool_spec.requires_approval:
            return PolicyDecision(
                decision=PolicyDecisionEnum.REQUIRE_APPROVAL,
                reason="Tool requires explicit approval.",
            )

        return PolicyDecision(
            decision=PolicyDecisionEnum.ALLOW,
            reason=(
                "Permission granted by role and policies."
            ),
        )

