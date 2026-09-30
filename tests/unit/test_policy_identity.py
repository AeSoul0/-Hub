"""
@file tests/unit/test_policy_identity.py
@description Unit tests for identity, RBAC, workspace isolation
and delegated subagent capabilities.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.agent_engine.models import ToolProposal, ToolSpec
from app.core.security import (
    BudgetState,
    IdentityService,
    Permission,
    PolicyEngine,
    Principal,
    SubagentCapabilitySet,
    TaskExecutionContext,
    WorkspacePolicy,
)


def make_tool(
    name: str = "safe_tool",
    risk: str = "LOW",
    *,
    network: bool = False,
    filesystem: bool = False,
    permissions=None,
    max_cost: float = 0.0,
    requires_approval: bool = False,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        version="1",
        description="test tool",
        input_schema={},
        output_schema={},
        risk_level=risk,
        permissions=permissions or [],
        network_access=network,
        filesystem_access=filesystem,
        max_runtime=10,
        max_output=1000,
        max_cost=max_cost,
        idempotent=False,
        requires_approval=requires_approval,
        sandbox_profile="default",
        audit_policy="default",
    )


def make_proposal(tool_name: str = "safe_tool") -> ToolProposal:
    return ToolProposal(
        tool_call_id="call-1",
        tool_name=tool_name,
        arguments={},
        run_id="run-1",
    )


def test_principal_instantiation():
    principal = Principal(
        id="usr-123",
        role="user",
        workspace_id="ws-99",
    )

    assert principal.id == "usr-123"
    assert principal.role.value == "user"
    assert principal.workspace_id == "ws-99"


def test_user_can_execute_safe_tool():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=10),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "ALLOW"


def test_user_cannot_execute_sensitive_tool():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(name="dangerous", risk="HIGH"),
        make_proposal("dangerous"),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=10),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"


def test_admin_sensitive_tool_requires_approval():
    principal = Principal(
        id="admin-1",
        role="admin",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(
            name="dangerous",
            risk="HIGH",
            requires_approval=True,
        ),
        make_proposal("dangerous"),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=10),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "REQUIRE_APPROVAL"


def test_workspace_isolation_denies_cross_workspace_execution():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-2"),
        BudgetState(),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"


def test_tool_proposal_must_match_spec():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(name="safe_tool"),
        make_proposal("other_tool"),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"


def test_budget_is_enforced_before_execution():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(max_cost=5),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=4),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"
    assert "budget" in decision.reason.lower()


def test_network_access_requires_permission():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(network=True),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"
    assert "NETWORK_ACCESS" in decision.reason


def test_filesystem_access_requires_permission():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(filesystem=True),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(),
        TaskExecutionContext(workspace_id="ws-1"),
    )

    assert decision.decision == "DENY"
    assert "FILESYSTEM_ACCESS" in decision.reason


def test_subagent_capabilities_are_enforced():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    capabilities = SubagentCapabilitySet(
        allowed_tools=["safe_tool"],
        allowed_scopes=["workspace"],
        max_budget=5,
        max_runtime=30,
        workspace="ws-1",
        permissions=[
            Permission.EXECUTE_SAFE_TOOL.value,
        ],
    )

    context = TaskExecutionContext(
        is_subagent=True,
        subagent_capabilities=capabilities,
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=5),
        context,
    )

    assert decision.decision == "ALLOW"


def test_subagent_cannot_escape_delegated_tools():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    capabilities = SubagentCapabilitySet(
        allowed_tools=["safe_tool"],
        allowed_scopes=["workspace"],
        max_budget=5,
        max_runtime=30,
        workspace="ws-1",
        permissions=[
            Permission.EXECUTE_SAFE_TOOL.value,
        ],
    )

    context = TaskExecutionContext(
        is_subagent=True,
        subagent_capabilities=capabilities,
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(name="other_tool"),
        make_proposal("other_tool"),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=5),
        context,
    )

    assert decision.decision == "DENY"


def test_subagent_workspace_mismatch_is_denied():
    principal = Principal(
        id="usr-1",
        role="user",
        workspace_id="ws-1",
    )

    capabilities = SubagentCapabilitySet(
        allowed_tools=["safe_tool"],
        allowed_scopes=["workspace"],
        max_budget=5,
        max_runtime=30,
        workspace="ws-2",
        permissions=[
            Permission.EXECUTE_SAFE_TOOL.value,
        ],
    )

    context = TaskExecutionContext(
        is_subagent=True,
        subagent_capabilities=capabilities,
        workspace_id="ws-1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(),
        make_proposal(),
        WorkspacePolicy(workspace_id="ws-1"),
        BudgetState(remaining=5),
        context,
    )

    assert decision.decision == "DENY"


def test_capability_intersection_narrows_tools_budget_runtime_and_permissions():
    parent = SubagentCapabilitySet(
        allowed_tools=["*"],
        allowed_scopes=["workspace", "project"],
        max_budget=20,
        max_runtime=120,
        workspace="ws-1",
        permissions=[
            Permission.EXECUTE_SAFE_TOOL.value,
            Permission.READ_MEMORY.value,
        ],
    )

    delegated = SubagentCapabilitySet(
        allowed_tools=["safe_tool"],
        allowed_scopes=["workspace"],
        max_budget=5,
        max_runtime=30,
        workspace="ws-1",
        permissions=[
            Permission.EXECUTE_SAFE_TOOL.value,
        ],
    )

    effective = SubagentCapabilitySet.intersect(
        parent,
        delegated,
        WorkspacePolicy(workspace_id="ws-1"),
    )

    assert effective.allowed_tools == ["safe_tool"]
    assert effective.allowed_scopes == ["workspace"]
    assert effective.max_budget == 5
    assert effective.max_runtime == 30
    assert effective.permissions == [
        Permission.EXECUTE_SAFE_TOOL.value
    ]
    assert effective.workspace == "ws-1"


def test_capability_intersection_rejects_cross_workspace_delegation():
    parent = SubagentCapabilitySet(
        allowed_tools=["*"],
        allowed_scopes=["workspace"],
        max_budget=10,
        max_runtime=60,
        workspace="ws-1",
        permissions=[Permission.EXECUTE_SAFE_TOOL.value],
    )

    delegated = SubagentCapabilitySet(
        allowed_tools=["safe_tool"],
        allowed_scopes=["workspace"],
        max_budget=5,
        max_runtime=30,
        workspace="ws-2",
        permissions=[Permission.EXECUTE_SAFE_TOOL.value],
    )

    with pytest.raises(ValueError, match="workspace"):
        SubagentCapabilitySet.intersect(
            parent,
            delegated,
            WorkspacePolicy(),
        )


def test_validate_expired_session_returns_none():
    db = MagicMock()

    session = MagicMock()
    session.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.query.return_value.filter.return_value.first.return_value = session

    assert IdentityService.validate_session(db, "expired") is None
    db.delete.assert_called_once_with(session)
    db.commit.assert_called_once()


def test_validate_missing_session_returns_none():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert IdentityService.validate_session(db, "missing") is None