"""
@file backend/app/agent_engine/runtime_tools.py
@description The tools of a run (part of AgentRuntime, Q1): which tools
the model sees, and the execution of one proposal through the Tool Gateway.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.agent_engine.delegation import (
    DELEGATE_TOOL,
    DelegationScope,
    clear_delegation_scope,
    set_delegation_scope,
)
from app.agent_engine.control import (
    RunLimits,
)
from app.agent_engine.errors import (
    ApprovalRequiredError,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.models import (
    AgentRun,
    Observation,
    ToolProposal,
    ToolSpec,
)
from app.core.security import (
    BudgetState,
    PolicyEngine,
    Principal,
    SubagentCapabilitySet,
    TaskExecutionContext,
    workspace_policy,
)
from app.runtime.tool_gateway import ToolInvocation
from app.skills.memory_skill import (
    clear_memory_context,
    set_memory_context,
)
from app.skills.registry import skill_registry


logger = logging.getLogger(__name__)

# Limits of a registered tool that does not declare its own.
DEFAULT_TOOL_RUNTIME = 30
DEFAULT_MAX_OUTPUT = 4000
DEFAULT_TOOL_COST = 0.0


class ToolsMixin:
    """
    Tool resolution and execution for AgentRuntime: specs built from the
    registered metadata, the tools exposed to the model, and each proposal
    run through the Tool Gateway with its delegation scope.
    """

    @staticmethod
    def _resolve_tool(tool_name: str) -> Tuple[Any, Any]:
        """
        Resolve a registered executable tool through the public SkillRegistry API.

        Unknown tools fail closed before execution.
        """
        try:
            tool = skill_registry.get_tool(tool_name)
            metadata = skill_registry.get_tool_metadata(tool_name)
        except Exception as exc:
            raise ValueError(
                f"Tool '{tool_name}' is not registered in SkillRegistry."
            ) from exc

        if tool is None:
            raise ValueError(
                f"Tool '{tool_name}' has no executable implementation."
            )

        if metadata is None:
            raise ValueError(
                f"Tool '{tool_name}' has no security metadata."
            )

        return tool, metadata

    @classmethod
    def _build_tool_spec(
        cls,
        tool_name: str,
    ) -> ToolSpec:
        """
        Convert SkillRegistry metadata into the canonical ToolSpec contract.
        """
        _, metadata = cls._resolve_tool(tool_name)

        risk_level = getattr(
            metadata.risk_level,
            "value",
            metadata.risk_level,
        )

        input_schema = getattr(
            metadata,
            "input_schema",
            {},
        ) or {}

        output_schema = getattr(
            metadata,
            "output_schema",
            {},
        ) or {}

        permissions = list(
            getattr(
                metadata,
                "permissions_required",
                [],
            )
            or []
        )

        return ToolSpec(
            name=metadata.name,
            version=str(
                getattr(
                    metadata,
                    "version",
                    "1.0.0",
                )
            ),
            description=metadata.description,
            input_schema=input_schema,
            output_schema=output_schema,
            risk_level=str(risk_level).upper(),
            permissions=permissions,
            network_access=bool(
                getattr(
                    metadata,
                    "network_access",
                    False,
                )
            ),
            filesystem_access=bool(
                getattr(
                    metadata,
                    "filesystem_access",
                    False,
                )
            ),
            max_runtime=int(
                getattr(
                    metadata,
                    "max_runtime",
                    DEFAULT_TOOL_RUNTIME,
                )
            ),
            max_output=int(
                getattr(
                    metadata,
                    "max_output",
                    DEFAULT_MAX_OUTPUT,
                )
            ),
            max_cost=float(
                getattr(
                    metadata,
                    "max_cost",
                    DEFAULT_TOOL_COST,
                )
            ),
            idempotent=bool(
                getattr(
                    metadata,
                    "idempotent",
                    False,
                )
            ),
            requires_approval=bool(
                getattr(
                    metadata,
                    "requires_approval",
                    False,
                )
            ),
            sandbox_profile=str(
                getattr(
                    metadata,
                    "sandbox_profile",
                    "default",
                )
            ),
            audit_policy=str(
                getattr(
                    metadata,
                    "audit_policy",
                    "standard",
                )
            ),
            untrusted_output=cls._is_untrusted_output(metadata),
            modifies_files=bool(
                getattr(
                    metadata,
                    "modifies_files",
                    False,
                )
            ),
        )

    @staticmethod
    def _is_untrusted_output(metadata: Any) -> bool:
        """
        Provenance of a tool's output: explicit metadata wins, otherwise
        anything read from the network or the filesystem is untrusted.
        """
        declared = getattr(metadata, "untrusted_output", None)

        if declared is not None:
            return bool(declared)

        return bool(
            getattr(metadata, "network_access", False)
            or getattr(metadata, "filesystem_access", False)
        )

    @classmethod
    def _build_model_tools(
        cls,
        principal: Principal,
        capabilities: Optional[SubagentCapabilitySet] = None,
        exposed_tools: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build the function-tool definitions the Worker model may call.

        Only registered tools that the PolicyEngine does not deny for this
        Principal (tools disabled in the Control Plane are denied) (and, for a subagent, its delegated capability set) are
        exposed, and only those the skill index picked for the run when it
        picked any. Exposure is not authorization: every call still goes
        through the ToolGateway pipeline.
        """
        model_tools: List[Dict[str, Any]] = []
        delegation_off = RunLimits.from_env().max_subagents <= 0

        for tool_name in skill_registry.get_registered_tool_names():
            if exposed_tools is not None and tool_name not in exposed_tools:
                continue

            # Delegation is one level deep (F8): a subagent never sees it.
            if tool_name == DELEGATE_TOOL and (capabilities is not None or delegation_off):
                continue

            try:
                spec = cls._build_tool_spec(tool_name)
            except ValueError:
                continue

            decision = PolicyEngine.authorize_tool(
                principal=principal,
                tool_spec=spec,
                tool_proposal=ToolProposal(
                    tool_call_id="exposure-check",
                    tool_name=tool_name,
                    arguments={},
                    run_id="exposure-check",
                ),
                workspace_policy=workspace_policy(),
                budget_state=BudgetState(),
                task_context=TaskExecutionContext(
                    is_subagent=capabilities is not None,
                    subagent_capabilities=capabilities,
                ),
            )

            if getattr(decision.decision, "value", decision.decision) == "DENY":
                continue

            model_tools.append(
                {
                    "type": "function",
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_schema
                    or {"type": "object", "properties": {}},
                }
            )

        return model_tools

    @staticmethod
    async def _execute_registered_tool(
        tool: Any,
        arguments: Dict[str, Any],
        session_id: str,
        workspace_id: str,
        principal_id: Optional[str] = None,
        trusted: bool = True,
    ) -> Any:
        """
        Execute a registered tool while exposing a trusted memory context.

        Memory context is installed only for the duration of the concrete tool
        execution and is always cleared afterwards. trusted is False once the
        run context holds untrusted content, so memories written from then on
        are stored as untrusted.
        """
        set_memory_context(
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            trusted=trusted,
        )

        try:
            if hasattr(tool, "ainvoke"):
                return await tool.ainvoke(arguments)

            if inspect.iscoroutinefunction(tool):
                return await tool(**arguments)

            return await asyncio.to_thread(
                tool,
                **arguments,
            )
        finally:
            clear_memory_context()

    @staticmethod
    def _input_channel(worker_context: Dict[str, Any]) -> str:
        """
        How the run's task arrived: "voice" for a transcript, else "text".
        """
        task = worker_context.get("task")
        channel = task.get("input_channel") if isinstance(task, dict) else None
        return "voice" if channel == "voice" else "text"

    async def _execute_proposal(
        self,
        proposal: ToolProposal,
        principal: Principal,
        session_id: str,
        workspace_id: str,
        run_id: str,
        untrusted_context: bool = False,
        capabilities: Optional[SubagentCapabilitySet] = None,
        input_channel: str = "text",
        exposed_tools: Optional[List[str]] = None,
        delegation: Optional[DelegationScope] = None,
    ) -> Observation:
        """
        Run one proposal through the ToolGateway and return its Observation.

        ApprovalRequiredError propagates to the caller; any other failure
        becomes an observation the model can react to. `delegation` is
        installed for the call, so delegate_task can start a subagent.
        """
        trusted = True
        succeeded = False
        modified_file: Optional[str] = None

        try:
            tool, _ = self._resolve_tool(
                proposal.tool_name
            )

            spec = self._build_tool_spec(
                proposal.tool_name
            )

            trusted = not spec.untrusted_output

            invocation = ToolInvocation(
                tool_name=proposal.tool_name,
                arguments=dict(
                    proposal.arguments
                ),
                principal=principal,
                session_id=session_id,
                spec=spec,
                tool_call_id=proposal.tool_call_id,
                run_id=run_id,
            )

            EventDispatcher().dispatch(
                "tool.proposed",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                tool=proposal.tool_name,
            )

            async def executor(
                **arguments: Any,
            ) -> Any:
                set_delegation_scope(delegation)

                try:
                    return await self._execute_registered_tool(
                        tool=tool,
                        arguments=arguments,
                        session_id=session_id,
                        workspace_id=workspace_id,
                        principal_id=principal.id,
                        trusted=not untrusted_context,
                    )
                finally:
                    clear_delegation_scope()

            tool_result = await self.tool_gateway.execute(
                invocation,
                executor,
                task_context=TaskExecutionContext(
                    workspace_id=workspace_id,
                    untrusted_context=untrusted_context,
                    is_subagent=capabilities is not None,
                    subagent_capabilities=capabilities,
                    input_channel=input_channel,
                    exposed_tools=exposed_tools,
                ),
            )

            content = (
                tool_result.output
                if tool_result.success
                else tool_result.error
            )

            succeeded = bool(tool_result.success)

            if succeeded:
                modified_file = self._file_target(proposal)

        except ApprovalRequiredError:
            raise

        except Exception as exc:  # noqa: BLE001 - a tool error becomes an observation for the model
            logger.warning("Tool %s failed: %s", proposal.tool_name, exc)
            content = f"Tool execution failed: {exc}"

        return Observation(
            tool_call_id=proposal.tool_call_id,
            tool_name=proposal.tool_name,
            arguments=dict(proposal.arguments),
            content=content,
            trusted=trusted,
            succeeded=succeeded,
            modified_file=modified_file,
        )

    def _delegation_scope(
        self,
        agent_run: AgentRun,
        principal: Principal,
        limits: RunLimits,
        capabilities: Optional[SubagentCapabilitySet],
    ) -> DelegationScope:
        """
        What delegate_task needs of the run calling it (F8).
        """
        return DelegationScope(
            parent_run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            principal=principal,
            usage=agent_run.usage,
            max_run_cost=limits.max_run_cost,
            max_subagents=limits.max_subagents,
            delegate=self.delegator,
            is_subagent=capabilities is not None,
        )

    @staticmethod
    def _record_observation(
        worker_context: Dict[str, Any],
        observation: Observation,
    ) -> None:
        """
        Append an observation and taint the run once untrusted content
        has entered the model context.
        """
        worker_context["observations"].append(
            observation
        )

        if not observation.trusted:
            worker_context["untrusted_context"] = True
