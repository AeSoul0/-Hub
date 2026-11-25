"""
@file backend/app/runtime/direct_tool.py
@description Runs one registered tool without a model, through the Tool Gateway.

Used where the user's intent is already exact: a button of the Casa page
(F7) or an instant command (V1, ADR-035). The call takes the same road as a
model's proposal: policy, schema check, approval when required, audit with
the hash chain. Only the model is skipped.
"""

from __future__ import annotations

from typing import Any, Dict

from app.core.security import Principal, TaskExecutionContext


def tool_spec(tool_name: str) -> Any:
    """The ToolSpec of a registered tool. ValueError when it is not available."""
    from app.agent_engine.runtime import AgentRuntime

    AgentRuntime._resolve_tool(tool_name)
    return AgentRuntime._build_tool_spec(tool_name)


def needs_approval(spec: Any) -> bool:
    return bool(spec.requires_approval or spec.risk_level in ("HIGH", "CRITICAL"))


async def run_tool(
    principal: Principal,
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    call_id: str,
    input_channel: str = "text",
) -> Any:
    """
    Execute a tool for this principal through the Tool Gateway and return its
    GatewayResult. Raises ValueError when the tool is not available and
    ApprovalRequiredError when the policy wants a human first.
    """
    from app.agent_engine.runtime import AgentRuntime
    from app.runtime.tool_gateway import ToolGateway, ToolInvocation

    tool, _ = AgentRuntime._resolve_tool(tool_name)
    spec = AgentRuntime._build_tool_spec(tool_name)
    context = TaskExecutionContext(workspace_id=principal.workspace_id, input_channel=input_channel)

    async def executor(**call: Any) -> Any:
        return await AgentRuntime._execute_registered_tool(
            tool=tool,
            arguments=call,
            session_id=session_id,
            workspace_id=principal.workspace_id,
            principal_id=principal.id,
        )

    invocation = ToolInvocation(
        tool_name=tool_name,
        arguments=dict(arguments),
        principal=principal,
        session_id=session_id,
        spec=spec,
        tool_call_id=call_id,
        run_id=run_id,
    )
    return await ToolGateway.execute(invocation, executor, task_context=context)


__all__ = ["needs_approval", "run_tool", "tool_spec"]
