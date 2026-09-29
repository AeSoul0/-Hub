"""
@file tests/unit/test_tool_gateway.py
@description Unit tests for Tool Gateway.

Implements core logic and architectural definitions.
"""
import pytest
import asyncio
from app.runtime.tool_gateway import ToolGateway, ToolInvocation, ToolResult
from app.core.security import Principal
from app.agent_engine.models import ToolSpec

def test_tool_gateway_sandbox_enforcement():
    gateway = ToolGateway()
    user = Principal(id="tester", role="user", workspace_id="ws-test")
    spec = ToolSpec(name="shell", version="1", description="", input_schema={}, output_schema={}, risk_level="HIGH", permissions=[], network_access=False, filesystem_access=False, max_runtime=1, max_output=1, max_cost=0, idempotent=False, requires_approval=False, sandbox_profile="", audit_policy="")
    invocation = ToolInvocation(tool_name="shell", arguments={"cmd": "rm -rf"}, principal=user, session_id="test", spec=spec)
    
    res = asyncio.run(gateway.execute(invocation, None))
    assert not res.success
    assert "Unauthorized" in res.error

def test_tool_gateway_budget_tracking():
    gateway = ToolGateway()
    user = Principal(id="tester", role="user", workspace_id="ws-test")
    spec = ToolSpec(name="costly", version="1", description="", input_schema={}, output_schema={}, risk_level="LOW", permissions=[], network_access=False, filesystem_access=False, max_runtime=1, max_output=1, max_cost=9999.0, idempotent=False, requires_approval=False, sandbox_profile="", audit_policy="")
    invocation = ToolInvocation(tool_name="costly", arguments={}, principal=user, session_id="123", spec=spec)
    
    res = asyncio.run(gateway.execute(invocation, None))
    assert not res.success
    assert "Budget exceeded" in res.error or "Unauthorized" in res.error
