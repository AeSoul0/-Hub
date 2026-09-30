"""
@file tests/unit/test_tool_gateway.py
@description Unit tests for the secure ToolGateway execution pipeline.

Covers identity, guardrails, idempotency, budget, approval, executor success,
and execution failure paths without requiring a live PostgreSQL connection.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent_engine.models import ToolSpec
from app.core.security import Principal
from app.runtime.tool_gateway import ToolGateway, ToolInvocation


# ==============================================================================
# TEST FIXTURES
# ==============================================================================

def make_spec(
    *,
    risk_level: str = "LOW",
    max_cost: float = 0.0,
    idempotent: bool = False,
    requires_approval: bool = False,
) -> ToolSpec:
    """Builds a complete ToolSpec using the canonical runtime schema."""
    return ToolSpec(
        name="test_tool",
        version="1.0.0",
        description="Test tool",
        input_schema={},
        output_schema={},
        risk_level=risk_level,
        permissions=[],
        network_access=False,
        filesystem_access=False,
        max_runtime=10,
        max_output=4000,
        max_cost=max_cost,
        idempotent=idempotent,
        requires_approval=requires_approval,
        sandbox_profile="default",
        audit_policy="standard",
    )


def make_invocation(
    *,
    spec: ToolSpec | None = None,
    arguments=None,
) -> ToolInvocation:
    """Build an isolated test invocation."""
    principal = Principal(
        id="tester",
        role="user",
        workspace_id="ws-test",
    )

    return ToolInvocation(
        tool_name="test_tool",
        arguments=arguments or {"value": "hello"},
        principal=principal,
        session_id="session-test",
        spec=spec or make_spec(),
        tool_call_id="call-test",
        run_id="run-test",
    )


def authorize_allow(*args, **kwargs):
    """Return a deterministic policy ALLOW decision for unit tests."""
    decision = MagicMock()
    decision.decision = "ALLOW"
    decision.reason = "test"
    return decision


# ==============================================================================
# TESTS
# ==============================================================================

def test_execute_success():
    """Verify a successful invocation crosses the full gateway pipeline."""
    invocation = make_invocation()

    async def executor(**kwargs):
        return "success_output"

    fake_task = MagicMock(id="task-1")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=authorize_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda name, args: args,
        ) as pre_guard,
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_post_execution",
            side_effect=lambda name, value: value,
        ) as post_guard,
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
            return_value=fake_task,
        ) as create_task,
        patch(
            "app.runtime.tool_gateway.TaskManager.update_state",
        ) as update_state,
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-1",
        ),
    ):
        result = asyncio.run(ToolGateway.execute(invocation, executor))

    assert result.success is True
    assert result.output == "success_output"
    assert result.audit_id == "audit-1"
    pre_guard.assert_called_once()
    post_guard.assert_called_once()
    create_task.assert_called_once()
    update_state.assert_called()


def test_execute_guardrail_denies_dangerous_input():
    """Verify dangerous tool parameters are denied before execution."""
    invocation = make_invocation(arguments={"cmd": "rm -rf /"})

    async def executor(**kwargs):
        raise AssertionError("Executor must not run")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=authorize_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=ValueError("dangerous command"),
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-deny",
        ),
    ):
        result = asyncio.run(ToolGateway.execute(invocation, executor))

    assert result.success is False
    assert "guardrail" in result.error.lower()
    assert result.audit_id == "audit-deny"


def test_execute_idempotency_returns_cached_result():
    """Verify a cached idempotent call never invokes the executor."""
    invocation = make_invocation(spec=make_spec(idempotent=True))

    async def executor(**kwargs):
        raise AssertionError("Cached invocation must not execute")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=authorize_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda name, args: args,
        ),
        patch(
            "app.runtime.tool_gateway.IdempotencyManager.get_result",
            return_value="cached-value",
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-cache",
        ),
    ):
        result = asyncio.run(ToolGateway.execute(invocation, executor))

    assert result.success is True
    assert result.output == "cached-value"
    assert result.audit_id == "audit-cache"


def test_execute_requires_approval():
    """Verify approval-gated tools pause before execution."""
    invocation = make_invocation(
        spec=make_spec(risk_level="HIGH", requires_approval=True),
    )

    async def executor(**kwargs):
        raise AssertionError("Approval-gated executor must not run")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=authorize_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda name, args: args,
        ),
        patch(
            "app.runtime.tool_gateway.ApprovalManager.check_approval_status",
            new=AsyncMock(return_value="NONE"),
        ),
        patch(
            "app.runtime.tool_gateway.ApprovalManager.request_approval",
            new=AsyncMock(return_value="approval-1"),
        ) as request_approval,
    ):
        try:
            asyncio.run(ToolGateway.execute(invocation, executor))
            assert False, "Expected approval pause"
        except Exception as exc:
            assert "requires human approval" in str(exc)

    request_approval.assert_awaited_once()


def test_execute_budget_denied_before_side_effect():
    """Verify insufficient budget prevents task creation and execution."""
    invocation = make_invocation(spec=make_spec(max_cost=100.0))

    async def executor(**kwargs):
        raise AssertionError("Budget-denied tool must not execute")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=authorize_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda name, args: args,
        ),
        patch(
            "app.runtime.tool_gateway.BudgetManager.get_remaining_budget",
            return_value=1.0,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-budget",
        ),
    ):
        result = asyncio.run(ToolGateway.execute(invocation, executor))

    assert result.success is False
    assert "Budget exceeded" in result.error