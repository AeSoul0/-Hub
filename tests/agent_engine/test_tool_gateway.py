"""
@file backend/tests/agent_engine/test_tool_gateway.py
@description Unit tests for ToolGateway.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.runtime.tool_gateway import ToolGateway, ToolInvocation, ToolResult
from app.core.security import Principal
from app.agent_engine.models import ToolSpec
from app.agent_engine.errors import ApprovalRequiredError

@pytest.fixture
def principal():
    return Principal(id="p1", role="user", workspace_id="w1", roles=["user"], permissions=["execute_tools"])

@pytest.fixture
def invocation(principal):
    return ToolInvocation(
        tool_name="test_tool",
        arguments={"arg1": "value1"},
        principal=principal,
        session_id="s1",
        spec=ToolSpec(name="test_tool", description="Test tool", risk="low", requires_approval=False)
    )

@pytest.mark.anyio
@patch('app.runtime.tool_gateway.PolicyEngine')
@patch('app.runtime.tool_gateway.ToolGuardrail')
@patch('app.runtime.tool_gateway.IdempotencyManager')
@patch('app.runtime.tool_gateway.ApprovalManager')
@patch('app.runtime.tool_gateway.TaskManager')
async def test_execute_success(mock_task, mock_approval, mock_idem, mock_guard, mock_policy, invocation):
    # Setup mocks
    mock_policy.evaluate.return_value.allowed = True
    mock_guard.validate_pre_execution.return_value = invocation.arguments
    mock_idem.get_result.return_value = None
    
    # Dummy tool handler
    async def dummy_handler(args):
        return "success_output"
        
    gateway = ToolGateway()
    result = await gateway.execute(invocation, dummy_handler)
    
    assert result.success is True
    assert result.output == "success_output"
    mock_policy.evaluate.assert_called_once()
    mock_guard.validate_pre_execution.assert_called_once()
    mock_idem.save_result.assert_called_once()

@pytest.mark.anyio
@patch('app.runtime.tool_gateway.PolicyEngine')
async def test_execute_policy_denied(mock_policy, invocation):
    mock_policy.evaluate.return_value.allowed = False
    mock_policy.evaluate.return_value.reason = "Not allowed"
    
    gateway = ToolGateway()
    result = await gateway.execute(invocation, None)
    
    assert result.success is False
    assert "Policy check failed" in result.error

@pytest.mark.anyio
@patch('app.runtime.tool_gateway.PolicyEngine')
@patch('app.runtime.tool_gateway.ApprovalManager')
async def test_execute_requires_approval(mock_approval, mock_policy, invocation):
    invocation.spec.requires_approval = True
    mock_policy.evaluate.return_value.allowed = True
    mock_approval.check_approval_status.return_value = "NONE"
    mock_approval.request_approval.return_value = "req_123"
    
    gateway = ToolGateway()
    with pytest.raises(ApprovalRequiredError):
        await gateway.execute(invocation, None)
        
    mock_approval.request_approval.assert_called_once()
