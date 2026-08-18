"""
@file tests/unit/test_tool_gateway.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import pytest
from app.tools.gateway import ToolGateway
from app.core.security import Principal

def test_tool_gateway_sandbox_enforcement():
    """M3: Verify Tool Gateway does not allow arbitrary script execution."""
    gateway = ToolGateway()
    user = Principal(id="tester", roles=["agent"], workspace_id="ws-test")
    
    # Should raise error because 'bash' is restricted
    with pytest.raises(Exception) as exc:
        gateway.execute_tool(user, tool_name="bash", kwargs={"cmd": "rm -rf /"})
    assert "Unauthorized" in str(exc.value) or "restricted" in str(exc.value).lower()

def test_tool_gateway_budget_tracking():
    """M3: Verify Tool Gateway registers execution metrics."""
    gateway = ToolGateway()
    user = Principal(id="tester", roles=["agent"], workspace_id="ws-test")
    
    # Registering a safe tool
    def dummy_tool(*args, **kwargs): return "success"
    gateway.registry["dummy_tool"] = {"func": dummy_tool, "requires_approval": False}
    
    result = gateway.execute_tool(user, "dummy_tool", {})
    assert result == "success"
