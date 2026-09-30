"""
@file backend/app/runtime/tool_gateway.py
@description Secure side-effect gateway for A.U.R.O.R.A. tool execution.

All executable tools cross this boundary before any external side effect:
identity -> policy -> guardrail -> schema -> budget -> approval ->
idempotency -> task tracking -> executor -> post-guardrail -> audit.

The gateway is intentionally framework-agnostic and receives an executor
callback from the native AgentRuntime.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field

from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.budget import BudgetManager
from app.agent_engine.errors import ApprovalRequiredError
from app.agent_engine.guardrails import ToolGuardrail
from app.agent_engine.models import ToolProposal, ToolSpec
from app.agent_engine.state.idempotency import IdempotencyManager
from app.core.security import (
    BudgetState,
    PolicyEngine,
    Principal,
    TaskExecutionContext,
    WorkspacePolicy,
)
from app.runtime.task_manager import TaskManager, TaskState


# ==============================================================================
# INVOCATION / RESULT CONTRACTS
# ==============================================================================


class ToolInvocation(BaseModel):
    """
    Represents one fully identified tool execution request.
    """

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    principal: Principal
    session_id: str
    spec: ToolSpec
    tool_call_id: str = "tool_call"
    run_id: str = "run_unknown"


class ToolResult(BaseModel):
    """
    Normalized result returned by the ToolGateway.
    """

    success: bool
    output: Any = None
    error: Optional[str] = None
    audit_id: Optional[str] = None


# ==============================================================================
# TOOL GATEWAY
# ==============================================================================


class ToolGateway:
    """
    Centralized policy and side-effect execution boundary.
    """

    @staticmethod
    def _idempotency_key(invocation: ToolInvocation) -> str:
        """
        Create a deterministic SHA-256 idempotency key scoped to the exact
        principal, workspace, run, and tool-call context.
        """
        payload = {
            "workspace_id": invocation.principal.workspace_id,
            "principal_id": invocation.principal.id,
            "run_id": invocation.run_id,
            "tool_call_id": invocation.tool_call_id,
            "tool": invocation.tool_name,
            "arguments": invocation.arguments,
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _audit_and_fail(
        invocation: ToolInvocation,
        error_message: str,
        decision: str = "DENY",
    ) -> ToolResult:
        """
        Record a rejected invocation and return a normalized failure.
        """
        audit_id = ToolGateway._log_audit(
            invocation=invocation,
            success=False,
            error=error_message,
            decision=decision,
        )

        return ToolResult(
            success=False,
            output=None,
            error=error_message,
            audit_id=audit_id,
        )

    @staticmethod
    def _log_audit(
        invocation: ToolInvocation,
        success: bool,
        error: Optional[str],
        decision: str = "ALLOW",
        execution_result: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> str:
        """
        Persist a structured audit record without storing raw arguments.
        """
        try:
            from app.core.db import SessionLocal
            from app.domain.models.audit import AuditLog

            arguments_hash = hashlib.sha256(
                json.dumps(
                    invocation.arguments,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()

            with SessionLocal() as db:
                record = AuditLog(
                    session_id=invocation.session_id,
                    run_id=invocation.run_id,
                    tool_call_id=invocation.tool_call_id,
                    principal_id=invocation.principal.id,
                    workspace_id=invocation.principal.workspace_id,
                    tool_name=invocation.tool_name,
                    risk=invocation.spec.risk_level,
                    arguments_hash=arguments_hash,
                    decision=decision,
                    success=success,
                    execution_result=execution_result,
                    duration=duration,
                    error=error,
                )

                db.add(record)
                db.commit()
                db.refresh(record)

                return record.id

        except Exception:
            # Audit persistence must never leak database internals.
            return "audit_failed"

    @staticmethod
    async def execute(
        invocation: ToolInvocation,
        executor_callback: Callable[..., Any],
        task_context: Optional[TaskExecutionContext] = None,
    ) -> ToolResult:
        """
        Execute a tool through the complete security pipeline.

        The executor is never called before policy, input guardrails,
        schema validation, budget checks, approval, and idempotency checks
        have completed successfully.
        """
        if invocation.principal is None:
            return ToolGateway._audit_and_fail(
                invocation,
                "Unauthorized: missing principal.",
            )

        if not invocation.principal.workspace_id:
            return ToolGateway._audit_and_fail(
                invocation,
                "Unauthorized: missing workspace binding.",
            )

        if task_context is None:
            task_context = TaskExecutionContext()

        proposal = ToolProposal(
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            arguments=dict(invocation.arguments),
            run_id=invocation.run_id,
        )

        # ----------------------------------------------------------------------
        # 1. Identity / policy
        # ----------------------------------------------------------------------
        decision = PolicyEngine.authorize_tool(
            principal=invocation.principal,
            tool_spec=invocation.spec,
            tool_proposal=proposal,
            workspace_policy=WorkspacePolicy(),
            budget_state=BudgetState(),
            task_context=task_context,
        )

        decision_value = (
            decision.decision.value
            if hasattr(decision.decision, "value")
            else str(decision.decision)
        )

        if decision_value == "DENY":
            return ToolGateway._audit_and_fail(
                invocation,
                f"Unauthorized: {decision.reason}",
                decision="DENY",
            )

        # ----------------------------------------------------------------------
        # 2. Pre-execution guardrail
        # ----------------------------------------------------------------------
        try:
            sanitized_arguments = ToolGuardrail.validate_pre_execution(
                invocation.tool_name,
                dict(invocation.arguments),
            )
        except Exception as exc:
            return ToolGateway._audit_and_fail(
                invocation,
                f"Tool guardrail rejected invocation: {exc}",
                decision="DENY",
            )

        invocation.arguments = dict(sanitized_arguments)

        # ----------------------------------------------------------------------
        # 3. Input schema validation
        # ----------------------------------------------------------------------
        if invocation.spec.input_schema:
            try:
                import jsonschema

                jsonschema.validate(
                    instance=invocation.arguments,
                    schema=invocation.spec.input_schema,
                )
            except Exception as exc:
                return ToolGateway._audit_and_fail(
                    invocation,
                    f"Schema validation failed: {exc}",
                    decision="DENY",
                )

        # ----------------------------------------------------------------------
        # 4. Idempotency lookup
        # ----------------------------------------------------------------------
        idem_key: Optional[str] = None

        if invocation.spec.idempotent:
            idem_key = ToolGateway._idempotency_key(invocation)
            cached = IdempotencyManager.get_result(idem_key)

            if cached is not None:
                audit_id = ToolGateway._log_audit(
                    invocation=invocation,
                    success=True,
                    error=None,
                    decision="CACHED",
                    execution_result=str(cached),
                )

                return ToolResult(
                    success=True,
                    output=cached,
                    audit_id=audit_id,
                )

        # ----------------------------------------------------------------------
        # 5. Budget preflight
        # ----------------------------------------------------------------------
        if invocation.spec.max_cost > 0:
            can_afford = BudgetManager.check_budget(
                invocation.principal.id,
                invocation.spec.max_cost,
            )

            if not can_afford:
                return ToolGateway._audit_and_fail(
                    invocation,
                    "Budget exceeded for this principal.",
                    decision="DENY",
                )

        # ----------------------------------------------------------------------
        # 6. Human approval
        # ----------------------------------------------------------------------
        if (
            invocation.spec.requires_approval
            or decision_value == "REQUIRE_APPROVAL"
        ):
            status = await ApprovalManager.check_approval_status(
                session_id=invocation.session_id,
                workspace_id=invocation.principal.workspace_id,
                principal_id=invocation.principal.id,
                run_id=invocation.run_id,
                tool_name=invocation.tool_name,
                arguments=invocation.arguments,
            )

            if status in {"NONE", "EXPIRED"}:
                await ApprovalManager.request_approval(
                    session_id=invocation.session_id,
                    workspace_id=invocation.principal.workspace_id,
                    principal_id=invocation.principal.id,
                    run_id=invocation.run_id,
                    tool_name=invocation.tool_name,
                    arguments=invocation.arguments,
                    risk=invocation.spec.risk_level,
                )

                raise ApprovalRequiredError(
                    f"Tool '{invocation.tool_name}' requires human approval."
                )

            if status == "WAITING_APPROVAL":
                raise ApprovalRequiredError(
                    f"Tool '{invocation.tool_name}' is waiting for human approval."
                )

            if status == "DENIED":
                return ToolGateway._audit_and_fail(
                    invocation,
                    "Tool approval was denied.",
                    decision="DENY",
                )

            if status != "APPROVED":
                return ToolGateway._audit_and_fail(
                    invocation,
                    "Approval state is invalid or unresolved.",
                    decision="DENY",
                )

        # ----------------------------------------------------------------------
        # 7. Atomic budget consumption
        # ----------------------------------------------------------------------
        if invocation.spec.max_cost > 0:
            consumed = BudgetManager.consume(
                invocation.principal.id,
                invocation.spec.max_cost,
            )

            if not consumed:
                return ToolGateway._audit_and_fail(
                    invocation,
                    "Budget became unavailable before execution.",
                    decision="DENY",
                )

        # ----------------------------------------------------------------------
        # 8. Durable task tracking
        # ----------------------------------------------------------------------
        task_record = TaskManager.create_task(
            session_id=invocation.session_id,
            payload={
                "tool": invocation.tool_name,
                "arguments": invocation.arguments,
                "run_id": invocation.run_id,
                "tool_call_id": invocation.tool_call_id,
            },
            priority=1,
            idempotency_key=idem_key,
        )

        TaskManager.update_state(
            task_record.id,
            TaskState.RUNNING,
        )

        start_time = time.monotonic()

        try:
            if executor_callback is None:
                raise RuntimeError("Tool executor callback is required.")

            raw_result = await executor_callback(
                **invocation.arguments,
            )

            # ------------------------------------------------------------------
            # 9. Post-execution guardrail
            # ------------------------------------------------------------------
            guarded_result = ToolGuardrail.validate_post_execution(
                invocation.tool_name,
                raw_result,
            )

            # ------------------------------------------------------------------
            # 10. Output size limit
            # ------------------------------------------------------------------
            normalized_output = str(guarded_result)

            if len(normalized_output) > invocation.spec.max_output:
                normalized_output = (
                    normalized_output[: invocation.spec.max_output]
                    + "... [TRUNCATED]"
                )

            # ------------------------------------------------------------------
            # 11. Durable idempotency result
            # ------------------------------------------------------------------
            if idem_key is not None:
                IdempotencyManager.save_result(
                    idem_key,
                    normalized_output,
                )

            duration_ms = int(
                (time.monotonic() - start_time) * 1000
            )

            TaskManager.update_state(
                task_record.id,
                TaskState.COMPLETED,
            )

            audit_id = ToolGateway._log_audit(
                invocation=invocation,
                success=True,
                error=None,
                decision="ALLOW",
                execution_result=normalized_output,
                duration=f"{duration_ms}ms",
            )

            return ToolResult(
                success=True,
                output=normalized_output,
                audit_id=audit_id,
            )

        except Exception as exc:
            duration_ms = int(
                (time.monotonic() - start_time) * 1000
            )

            try:
                TaskManager.update_state(
                    task_record.id,
                    TaskState.FAILED,
                    error_message=str(exc),
                )
            except Exception:
                pass

            audit_id = ToolGateway._log_audit(
                invocation=invocation,
                success=False,
                error=str(exc),
                decision="ERROR",
                duration=f"{duration_ms}ms",
            )

            return ToolResult(
                success=False,
                output=None,
                error=str(exc),
                audit_id=audit_id,
            )


__all__ = [
    "ToolGateway",
    "ToolInvocation",
    "ToolResult",
]