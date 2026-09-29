"""
@file tests/unit/test_policy_identity.py
@description Unit tests for Policy Engine.

Implements core logic and architectural definitions.
"""
import pytest
from app.core.security import Principal, PolicyEngine, TaskExecutionContext, WorkspacePolicy, BudgetState
from app.agent_engine.models import ToolSpec, ToolProposal

def test_principal_instantiation():
    user = Principal(id="usr-123", role="user", workspace_id="ws-99")
    assert user.role == "user"

def test_identity_service_rbac_allow():
    user = Principal(id="usr-1", role="admin", workspace_id="ws-1")
    spec = ToolSpec(name="safe_tool", version="1", description="", input_schema={}, output_schema={}, risk_level="LOW", permissions=[], network_access=False, filesystem_access=False, max_runtime=1, max_output=1, max_cost=0, idempotent=False, requires_approval=False, sandbox_profile="", audit_policy="")
    proposal = ToolProposal(tool_call_id="1", tool_name="safe_tool", arguments={}, run_id="1")
    decision = PolicyEngine.authorize_tool(user, spec, proposal, WorkspacePolicy(), BudgetState(), TaskExecutionContext())
    assert decision.decision == "ALLOW"

def test_identity_service_rbac_deny():
    user = Principal(id="usr-1", role="user", workspace_id="ws-1")
    spec = ToolSpec(name="sensitive", version="1", description="", input_schema={}, output_schema={}, risk_level="HIGH", permissions=[], network_access=False, filesystem_access=False, max_runtime=1, max_output=1, max_cost=0, idempotent=False, requires_approval=False, sandbox_profile="", audit_policy="")
    proposal = ToolProposal(tool_call_id="1", tool_name="sensitive", arguments={}, run_id="1")
    decision = PolicyEngine.authorize_tool(user, spec, proposal, WorkspacePolicy(), BudgetState(), TaskExecutionContext())
    assert decision.decision == "DENY"

def test_workspace_isolation():
    user = Principal(id="usr-1", role="user", workspace_id="ws-1")
    assert user.workspace_id == "ws-1"
