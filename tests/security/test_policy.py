"""
@file tests/security/test_policy.py
@description Unit tests for the canonical PolicyEngine contract.
"""

from app.agent_engine.models import ToolProposal, ToolSpec
from app.core.security import (
    BudgetState,
    PolicyEngine,
    Principal,
    TaskExecutionContext,
    WorkspacePolicy,
)


def make_tool(
    name: str = "safe_tool",
    risk: str = "LOW",
    *,
    requires_approval: bool = False,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        version="1",
        description="test tool",
        input_schema={},
        output_schema={},
        risk_level=risk,
        permissions=[],
        network_access=False,
        filesystem_access=False,
        max_runtime=10,
        max_output=1000,
        max_cost=0,
        idempotent=False,
        requires_approval=requires_approval,
        sandbox_profile="default",
        audit_policy="default",
    )


def make_proposal(
    tool_name: str = "safe_tool",
) -> ToolProposal:
    return ToolProposal(
        tool_call_id="call-1",
        tool_name=tool_name,
        arguments={},
        run_id="run-1",
    )


def test_policy_engine_allow_safe_tool():
    principal = Principal(
        id="u1",
        role="user",
        workspace_id="w1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(),
        make_proposal(),
        WorkspacePolicy(
            workspace_id="w1"
        ),
        BudgetState(
            remaining=10
        ),
        TaskExecutionContext(
            workspace_id="w1"
        ),
    )

    assert decision.decision == "ALLOW"


def test_policy_engine_deny_sensitive_tool_without_permission():
    principal = Principal(
        id="u1",
        role="user",
        workspace_id="w1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(
            name="dangerous_tool",
            risk="HIGH",
        ),
        make_proposal(
            "dangerous_tool"
        ),
        WorkspacePolicy(
            workspace_id="w1"
        ),
        BudgetState(
            remaining=10
        ),
        TaskExecutionContext(
            workspace_id="w1"
        ),
    )

    assert decision.decision == "DENY"
    assert "permission" in (
        decision.reason or ""
    ).lower()


def test_policy_engine_requires_approval_for_sensitive_tool_with_permission():
    principal = Principal(
        id="admin1",
        role="admin",
        workspace_id="w1",
    )

    decision = PolicyEngine.authorize_tool(
        principal,
        make_tool(
            name="dangerous_tool",
            risk="HIGH",
            requires_approval=True,
        ),
        make_proposal(
            "dangerous_tool"
        ),
        WorkspacePolicy(
            workspace_id="w1"
        ),
        BudgetState(
            remaining=10
        ),
        TaskExecutionContext(
            workspace_id="w1"
        ),
    )

    assert decision.decision == "REQUIRE_APPROVAL"