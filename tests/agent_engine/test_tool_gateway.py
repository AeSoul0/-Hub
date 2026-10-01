"""
@file tests/agent_engine/test_tool_gateway.py
@description Unit tests for the secure ToolGateway execution boundary.

The suite validates the canonical gateway contract:
identity -> policy -> guardrail -> schema -> idempotency ->
budget -> approval -> task tracking -> executor -> audit.

All tests isolate persistence and external side effects through mocks.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_engine.models import ToolSpec
from app.core.security import Principal
from app.runtime.tool_gateway import ToolGateway, ToolInvocation


# ==============================================================================
# TEST HELPERS
# ==============================================================================


def make_spec(
    *,
    risk_level: str = "LOW",
    max_cost: float = 0.0,
    idempotent: bool = False,
    requires_approval: bool = False,
) -> ToolSpec:
    """
    Build a complete ToolSpec using the canonical runtime contract.
    """
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
    arguments: dict | None = None,
) -> ToolInvocation:
    """
    Build an isolated ToolInvocation with complete security context.
    """
    principal = Principal(
        id="principal-test",
        role="user",
        workspace_id="workspace-test",
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


def policy_allow(*args, **kwargs):
    """
    Return a deterministic ALLOW decision for gateway unit tests.
    """
    decision = MagicMock()
    decision.decision = "ALLOW"
    decision.reason = "Unit-test authorization granted."
    return decision


# ==============================================================================
# CORE EXECUTION TESTS
# ==============================================================================


def test_execute_success():
    """
    Verify a valid invocation reaches the executor and returns a normalized result.
    """
    invocation = make_invocation()

    async def executor(**kwargs):
        return "success-output"

    task_record = MagicMock(id="task-test")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ) as pre_guard,
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_post_execution",
            side_effect=lambda tool_name, output: output,
        ) as post_guard,
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
            return_value=task_record,
        ) as create_task,
        patch(
            "app.runtime.tool_gateway.TaskManager.update_state",
        ) as update_state,
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-success",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is True
    assert result.output == "success-output"
    assert result.audit_id == "audit-success"

    pre_guard.assert_called_once()
    post_guard.assert_called_once()
    create_task.assert_called_once()
    update_state.assert_called()


def test_execute_policy_denied_before_side_effect():
    """
    Verify policy denial prevents guardrails, task creation, and execution.
    """
    invocation = make_invocation()

    async def executor(**kwargs):
        raise AssertionError("Executor must not be called.")

    decision = MagicMock()
    decision.decision = "DENY"
    decision.reason = "Permission denied."

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            return_value=decision,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
        ) as pre_guard,
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
        ) as create_task,
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-deny",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is False
    assert "Unauthorized" in result.error
    assert result.audit_id == "audit-deny"

    pre_guard.assert_not_called()
    create_task.assert_not_called()


def test_execute_guardrail_denied_before_side_effect():
    """
    Verify pre-execution guardrails reject dangerous arguments before execution.
    """
    invocation = make_invocation(
        arguments={"cmd": "rm -rf /"},
    )

    async def executor(**kwargs):
        raise AssertionError("Executor must not be called.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=ValueError("dangerous command"),
        ),
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
        ) as create_task,
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-guardrail",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is False
    assert "guardrail" in result.error.lower()
    assert result.audit_id == "audit-guardrail"
    create_task.assert_not_called()


# ==============================================================================
# IDEMPOTENCY TESTS
# ==============================================================================


def test_idempotency_key_is_scoped_to_execution_identity():
    """
    Verify the idempotency key changes when principal, run, or tool-call identity
    changes, preventing cross-run or cross-principal cache collisions.
    """
    first = make_invocation(
        spec=make_spec(idempotent=True),
    )

    same_request = make_invocation(
        spec=make_spec(idempotent=True),
    )

    different_principal = make_invocation(
        spec=make_spec(idempotent=True),
    )
    different_principal.principal = Principal(
        id="principal-other",
        role="user",
        workspace_id="workspace-test",
    )

    different_run = make_invocation(
        spec=make_spec(idempotent=True),
    )
    different_run.run_id = "run-other"

    different_tool_call = make_invocation(
        spec=make_spec(idempotent=True),
    )
    different_tool_call.tool_call_id = "call-other"

    first_key = ToolGateway._idempotency_key(first)

    assert first_key == ToolGateway._idempotency_key(same_request)
    assert first_key != ToolGateway._idempotency_key(different_principal)
    assert first_key != ToolGateway._idempotency_key(different_run)
    assert first_key != ToolGateway._idempotency_key(different_tool_call)


def test_execute_idempotent_call_returns_cached_result():
    """
    Verify a cached idempotent invocation never reaches the executor.
    """
    invocation = make_invocation(
        spec=make_spec(idempotent=True),
    )

    async def executor(**kwargs):
        raise AssertionError("Cached invocation must not execute.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ),
        patch(
            "app.runtime.tool_gateway.IdempotencyManager.get_result",
            return_value="cached-output",
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-cache",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is True
    assert result.output == "cached-output"
    assert result.audit_id == "audit-cache"


# ==============================================================================
# APPROVAL TESTS
# ==============================================================================


def test_execute_requires_approval_and_preserves_full_context():
    """
    Verify a new approval request contains session, workspace, principal,
    run, tool, arguments, and risk context.
    """
    invocation = make_invocation(
        spec=make_spec(
            risk_level="HIGH",
            requires_approval=True,
        ),
    )

    async def executor(**kwargs):
        raise AssertionError("Approval-gated executor must not execute.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
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
        with pytest.raises(Exception, match="requires human approval"):
            asyncio.run(
                ToolGateway.execute(
                    invocation,
                    executor,
                )
            )

    request_approval.assert_awaited_once()

    kwargs = request_approval.await_args.kwargs

    assert kwargs["session_id"] == "session-test"
    assert kwargs["workspace_id"] == "workspace-test"
    assert kwargs["principal_id"] == "principal-test"
    assert kwargs["run_id"] == "run-test"
    assert kwargs["tool_name"] == "test_tool"
    assert kwargs["arguments"] == {"value": "hello"}
    assert kwargs["risk"] == "HIGH"


def test_execute_denied_approval_blocks_executor():
    """
    Verify an explicit DENIED approval state fails closed.
    """
    invocation = make_invocation(
        spec=make_spec(
            risk_level="HIGH",
            requires_approval=True,
        ),
    )

    async def executor(**kwargs):
        raise AssertionError("Denied approval must not execute.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ),
        patch(
            "app.runtime.tool_gateway.ApprovalManager.check_approval_status",
            new=AsyncMock(return_value="DENIED"),
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-denied",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is False
    assert "approval was denied" in result.error.lower()
    assert result.audit_id == "audit-denied"


def test_execute_unknown_approval_state_fails_closed():
    """
    Verify unexpected approval states never authorize execution.
    """
    invocation = make_invocation(
        spec=make_spec(
            risk_level="HIGH",
            requires_approval=True,
        ),
    )

    async def executor(**kwargs):
        raise AssertionError("Unknown approval state must not execute.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ),
        patch(
            "app.runtime.tool_gateway.ApprovalManager.check_approval_status",
            new=AsyncMock(return_value="UNKNOWN"),
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-unknown",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is False
    assert "approval" in result.error.lower()
    assert result.audit_id == "audit-unknown"


# ==============================================================================
# BUDGET TESTS
# ==============================================================================


def test_execute_budget_denied_before_side_effect():
    """
    Verify insufficient budget prevents executor and task creation.
    """
    invocation = make_invocation(
        spec=make_spec(max_cost=100.0),
    )

    async def executor(**kwargs):
        raise AssertionError("Budget-denied tool must not execute.")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ),
        patch(
            "app.runtime.tool_gateway.BudgetManager.check_budget",
            return_value=False,
        ),
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
        ) as create_task,
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-budget",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is False
    assert "budget" in result.error.lower()
    create_task.assert_not_called()


def test_execute_consumes_budget_only_after_approval():
    """
    Verify budget consumption occurs only after authorization and approval.
    """
    invocation = make_invocation(
        spec=make_spec(
            risk_level="HIGH",
            max_cost=2.5,
            requires_approval=True,
        ),
    )

    async def executor(**kwargs):
        return "executed"

    task_record = MagicMock(id="task-budget")

    with (
        patch(
            "app.runtime.tool_gateway.PolicyEngine.authorize_tool",
            side_effect=policy_allow,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_pre_execution",
            side_effect=lambda tool_name, arguments: arguments,
        ),
        patch(
            "app.runtime.tool_gateway.BudgetManager.check_budget",
            return_value=True,
        ),
        patch(
            "app.runtime.tool_gateway.BudgetManager.consume",
            return_value=True,
        ) as consume_budget,
        patch(
            "app.runtime.tool_gateway.ApprovalManager.check_approval_status",
            new=AsyncMock(return_value="APPROVED"),
        ),
        patch(
            "app.runtime.tool_gateway.TaskManager.create_task",
            return_value=task_record,
        ),
        patch(
            "app.runtime.tool_gateway.TaskManager.update_state",
        ),
        patch(
            "app.runtime.tool_gateway.ToolGuardrail.validate_post_execution",
            side_effect=lambda tool_name, output: output,
        ),
        patch(
            "app.runtime.tool_gateway.ToolGateway._log_audit",
            return_value="audit-budget-success",
        ),
    ):
        result = asyncio.run(
            ToolGateway.execute(
                invocation,
                executor,
            )
        )

    assert result.success is True
    assert result.output == "executed"
    consume_budget.assert_called_once_with(
        "principal-test",
        2.5,
    )