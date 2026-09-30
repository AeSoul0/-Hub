"""
@file backend/tests/security/test_policy.py
@description Unit tests for PolicyEngine and permissions.
"""
import pytest
from app.core.security import PolicyEngine, Principal, Permission
from app.agent_engine.models import ToolSpec

def test_policy_engine_allow_safe_tool():
    principal = Principal(id="u1", role="user", workspace_id="w1", roles=["user"], permissions=[Permission.EXECUTE_SAFE_TOOL])
    spec = ToolSpec(name="safe_tool", description="Safe tool", risk="low", requires_approval=False)
    
    decision = PolicyEngine.authorize_tool(principal, spec)
    assert decision.status == "ALLOW"
    assert decision.allowed is True

def test_policy_engine_deny_sensitive_tool_without_permission():
    principal = Principal(id="u1", role="user", workspace_id="w1", roles=["user"], permissions=[Permission.EXECUTE_SAFE_TOOL])
    spec = ToolSpec(name="dangerous_tool", description="Dangerous tool", risk="high", requires_approval=True)
    
    decision = PolicyEngine.authorize_tool(principal, spec)
    assert decision.status == "DENY"
    assert decision.allowed is False
    assert "Missing required permission" in decision.reason

def test_policy_engine_allow_sensitive_tool_with_permission():
    principal = Principal(id="admin1", role="admin", workspace_id="w1", roles=["admin"], permissions=[Permission.EXECUTE_SENSITIVE_TOOL, Permission.EXECUTE_SAFE_TOOL])
    spec = ToolSpec(name="dangerous_tool", description="Dangerous tool", risk="high", requires_approval=True)
    
    decision = PolicyEngine.authorize_tool(principal, spec)
    # The ToolGateway will handle the actual approval pause. PolicyEngine just checks permissions.
    assert decision.status == "ALLOW"
    assert decision.allowed is True
