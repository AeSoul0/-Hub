"""
@file backend/app/agent_engine/runtime.py
@description Native A.U.R.O.R.A. Agent Execution Runtime.

This module implements the deterministic Worker -> ToolGateway -> Checker
execution loop without using LangGraph as an execution authority.

Security invariants enforced here include:

- explicit authenticated Principal;
- persisted run/session/workspace/principal consistency;
- explicit execution run IDs;
- trusted runtime context propagation;
- tool proposal/run consistency;
- durable execution state;
- bounded retries and turns;
- memory context scoped to the authenticated session and workspace.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.adapters.openai_adapter import OpenAIAdapter
from app.agent_engine.checker import AgentChecker
from app.agent_engine.errors import (
    ApprovalRequiredError,
    MaxTurnsReachedError,
    TaskTimeoutError,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.guardrails import InputGuardrail, OutputGuardrail
from app.agent_engine.models import (
    AgentRun,
    AgentRunStatus,
    CheckerDecisionEnum,
    Observation,
    ToolProposal,
    ToolSpec,
)
from app.agent_engine.resources import ResourceManager
from app.agent_engine.state.manager import AgentStateManager
from app.agents.subagents.base import SubagentFactory
from app.core.security import Principal, SubagentCapabilitySet
from app.runtime.tool_gateway import ToolGateway, ToolInvocation
from app.skills.memory_skill import (
    clear_memory_context,
    set_memory_context,
)
from app.skills.registry import skill_registry


# ==============================================================================
# EXECUTION DEFAULTS
# ==============================================================================

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_TOOL_CALLS = 5
DEFAULT_TOOL_RUNTIME = 30
DEFAULT_MAX_OUTPUT = 4000
DEFAULT_TOOL_COST = 0.0


# ==============================================================================
# AGENT RUNTIME
# ==============================================================================


class AgentRuntime:
    """
    Native deterministic execution kernel.

    The runtime owns orchestration state while the ToolGateway owns side
    effects and the independent Checker owns acceptance decisions.
    """

    def __init__(
        self,
        db_session: Any = None,
        tool_gateway: Optional[ToolGateway] = None,
    ) -> None:
        self.db = db_session
        self.tool_gateway = tool_gateway or ToolGateway()

    # ==========================================================================
    # TOOL RESOLUTION
    # ==========================================================================

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
        )

    @staticmethod
    async def _execute_registered_tool(
        tool: Any,
        arguments: Dict[str, Any],
        session_id: str,
        workspace_id: str,
    ) -> Any:
        """
        Execute a registered tool while exposing a trusted memory context.

        Memory context is installed only for the duration of the concrete tool
        execution and is always cleared afterwards.
        """
        set_memory_context(
            session_id=session_id,
            workspace_id=workspace_id,
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

    # ==========================================================================
    # MAIN EXECUTION LOOP
    # ==========================================================================

    async def execute_task(
        self,
        task: Dict[str, Any],
        orchestrator: Any,
        worker: Any,
        checker: Any,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        timeout: Optional[float] = None,
        cancellation_token: Optional[Any] = None,
        run_id: Optional[str] = None,
        session_id: str = "",
        workspace_id: str = "",
        principal: Optional[Principal] = None,
    ) -> Any:
        """
        Execute one deterministic Worker -> ToolGateway -> Checker cycle.

        The Principal is mandatory. Existing persisted runs are accepted only
        when their session, workspace and principal identity match the current
        authenticated execution context.
        """
        del orchestrator

        if principal is None:
            raise PermissionError(
                "Authenticated Principal is required for agent execution."
            )

        if not isinstance(principal, Principal):
            raise PermissionError(
                "Execution Principal is invalid."
            )

        if not principal.id:
            raise PermissionError(
                "Execution Principal is missing an identity."
            )

        if not session_id:
            raise ValueError(
                "session_id is required."
            )

        if not workspace_id:
            raise ValueError(
                "workspace_id is required."
            )

        if principal.workspace_id != workspace_id:
            raise PermissionError(
                "Principal workspace does not match execution workspace."
            )

        if max_attempts <= 0:
            raise ValueError(
                "max_attempts must be greater than zero."
            )

        if max_turns <= 0:
            raise ValueError(
                "max_turns must be greater than zero."
            )

        if max_tool_calls <= 0:
            raise ValueError(
                "max_tool_calls must be greater than zero."
            )

        run_id = run_id or str(uuid.uuid4())

        agent_run = AgentStateManager.load_agent_run(
            run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal.id,
        )

        if agent_run is None:
            start_time = datetime.utcnow()
            current_attempt = 1
            turn = 0

            validated_description = InputGuardrail.validate(
                str(
                    task.get(
                        "description",
                        task,
                    )
                )
            )

            task = {
                **task,
                "description": validated_description,
            }

            worker_context: Dict[str, Any] = {
                "run_id": run_id,
                "session_id": session_id,
                "workspace_id": workspace_id,
                "principal_id": principal.id,
                "principal_role": principal.role.value,
                "task": task,
                "feedback": None,
                "observations": [],
                "resuming": False,
            }

            last_feedback: Optional[str] = None

            agent_run = AgentRun(
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal_id=principal.id,
                role=principal.role.value,
                status=AgentRunStatus.RUNNING,
                task_attempts=current_attempt,
                current_state={
                    "turn": turn,
                    "worker_context": worker_context,
                    "last_feedback": last_feedback,
                },
                created_at=start_time,
            )

            AgentStateManager.save_agent_run(
                agent_run
            )

            EventDispatcher().dispatch(
                "run.started",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )

        else:
            if agent_run.session_id != session_id:
                raise PermissionError(
                    "Persisted run session does not match the authenticated session."
                )

            if agent_run.workspace_id != workspace_id:
                raise PermissionError(
                    "Persisted run workspace does not match the execution workspace."
                )

            if agent_run.principal_id != principal.id:
                raise PermissionError(
                    "Persisted run principal does not match the authenticated Principal."
                )

            start_time = agent_run.created_at
            current_attempt = max(
                1,
                agent_run.task_attempts,
            )

            current_state = agent_run.current_state or {}

            turn = int(
                current_state.get(
                    "turn",
                    0,
                )
            )

            worker_context = current_state.get(
                "worker_context"
            ) or {
                "run_id": run_id,
                "session_id": session_id,
                "workspace_id": workspace_id,
                "principal_id": principal.id,
                "principal_role": principal.role.value,
                "task": task,
                "feedback": None,
                "observations": [],
                "resuming": True,
            }

            worker_context["run_id"] = run_id
            worker_context["session_id"] = session_id
            worker_context["workspace_id"] = workspace_id
            worker_context["principal_id"] = principal.id
            worker_context["principal_role"] = principal.role.value

            last_feedback = current_state.get(
                "last_feedback"
            )

            if agent_run.status == AgentRunStatus.COMPLETED:
                return agent_run.result

            if agent_run.status in {
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
                AgentRunStatus.EXPIRED,
            }:
                raise MaxTurnsReachedError(
                    f"Task {run_id} cannot resume from terminal state "
                    f"{agent_run.status.value}."
                )

            if agent_run.status == AgentRunStatus.WAITING_APPROVAL:
                agent_run.status = AgentRunStatus.RUNNING

                AgentStateManager.save_agent_run(
                    agent_run
                )

        while current_attempt <= max_attempts:
            if (
                cancellation_token is not None
                and getattr(
                    cancellation_token,
                    "is_cancelled",
                    False,
                )
            ):
                agent_run.status = AgentRunStatus.CANCELLED

                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                return None

            if timeout is not None:
                elapsed = (
                    datetime.utcnow() - start_time
                ).total_seconds()

                if elapsed >= timeout:
                    agent_run.status = AgentRunStatus.FAILED

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    raise TaskTimeoutError(
                        "Task execution exceeded configured timeout."
                    )

            worker_completed = False
            worker_result = None

            while turn < max_turns:
                turn += 1

                worker_context.update(
                    {
                        "run_id": run_id,
                        "session_id": session_id,
                        "workspace_id": workspace_id,
                        "principal_id": principal.id,
                        "principal_role": principal.role.value,
                    }
                )

                try:
                    if timeout is not None:
                        elapsed = (
                            datetime.utcnow() - start_time
                        ).total_seconds()

                        remaining = max(
                            0.1,
                            timeout - elapsed,
                        )

                        step_result = await asyncio.wait_for(
                            worker.generate(
                                worker_context
                            ),
                            timeout=remaining,
                        )
                    else:
                        step_result = await worker.generate(
                            worker_context
                        )

                except asyncio.TimeoutError as exc:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "TaskTimeoutError"
                    )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    raise TaskTimeoutError(
                        "Worker execution exceeded configured timeout."
                    ) from exc

                except Exception as exc:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        f"Worker failed: {exc}"
                    )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    break

                if not isinstance(step_result, dict):
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "Worker returned an invalid execution payload."
                    )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    break

                worker_context["resuming"] = False

                proposals = step_result.get(
                    "tool_proposals",
                    [],
                )

                if not proposals:
                    worker_result = step_result.get(
                        "output"
                    )
                    worker_completed = True

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    break

                if len(proposals) > max_tool_calls:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "Exceeded max tool calls per worker turn."
                    )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    break

                for proposal in proposals:
                    if not isinstance(
                        proposal,
                        ToolProposal,
                    ):
                        raise TypeError(
                            "Worker returned an invalid ToolProposal instance."
                        )

                    if proposal.run_id != run_id:
                        agent_run.status = AgentRunStatus.FAILED

                        self._save(
                            agent_run,
                            current_attempt,
                            turn,
                            worker_context,
                            last_feedback,
                        )

                        raise PermissionError(
                            "Tool proposal run_id does not match the active execution run."
                        )

                    try:
                        tool, _ = self._resolve_tool(
                            proposal.tool_name
                        )

                        spec = self._build_tool_spec(
                            proposal.tool_name
                        )

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
                            return await self._execute_registered_tool(
                                tool=tool,
                                arguments=arguments,
                                session_id=session_id,
                                workspace_id=workspace_id,
                            )

                        tool_result = await self.tool_gateway.execute(
                            invocation,
                            executor,
                        )

                        observation_content = (
                            tool_result.output
                            if tool_result.success
                            else tool_result.error
                        )

                        worker_context["observations"].append(
                            Observation(
                                tool_call_id=proposal.tool_call_id,
                                content=observation_content,
                            )
                        )

                    except ApprovalRequiredError:
                        agent_run.status = (
                            AgentRunStatus.WAITING_APPROVAL
                        )

                        EventDispatcher().dispatch(
                            "tool.approval_required",
                            run_id=run_id,
                            session_id=session_id,
                            workspace_id=workspace_id,
                            tool=proposal.tool_name,
                        )

                        worker_context["observations"].append(
                            Observation(
                                tool_call_id=proposal.tool_call_id,
                                content=(
                                    "Waiting for human approval."
                                ),
                            )
                        )

                        self._save(
                            agent_run,
                            current_attempt,
                            turn,
                            worker_context,
                            last_feedback,
                        )

                        return {
                            "status": "WAITING_APPROVAL",
                            "run_id": run_id,
                        }

                    except Exception as exc:
                        worker_context["observations"].append(
                            Observation(
                                tool_call_id=proposal.tool_call_id,
                                content=(
                                    f"Tool execution failed: {exc}"
                                ),
                            )
                        )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

            if not worker_completed:
                if (
                    agent_run.status
                    == AgentRunStatus.WAITING_APPROVAL
                ):
                    return {
                        "status": "WAITING_APPROVAL",
                        "run_id": run_id,
                    }

                if agent_run.status != AgentRunStatus.FAILED:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "Maximum turns reached."
                    )

                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                raise MaxTurnsReachedError(
                    f"Task {run_id} failed: maximum turns reached."
                )

            trace = [
                {
                    "tool_call_id": observation.tool_call_id,
                    "content": observation.content,
                }
                for observation in worker_context.get(
                    "observations",
                    [],
                )
            ]

            try:
                checker_decision = await checker.evaluate(
                    task=task,
                    result=worker_result,
                    trace=trace,
                )

            except Exception as exc:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append(
                    f"Checker failed: {exc}"
                )

                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                raise MaxTurnsReachedError(
                    f"Task {run_id} failed because the checker "
                    "could not produce a trusted decision."
                ) from exc

            if checker_decision.status == CheckerDecisionEnum.ACCEPT:
                guarded_result = OutputGuardrail.validate(
                    str(worker_result)
                )

                agent_run.status = AgentRunStatus.COMPLETED
                agent_run.result = guarded_result
                agent_run.error = None

                EventDispatcher().dispatch(
                    "checker.accepted",
                    run_id=run_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                )

                EventDispatcher().dispatch(
                    "run.completed",
                    run_id=run_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                )

                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                return guarded_result

            if checker_decision.status == CheckerDecisionEnum.FAIL:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.error = (
                    checker_decision.retry_instruction
                    or "Checker rejected the result as unrecoverable."
                )

                agent_run.errors.append(
                    agent_run.error
                )

                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                return None

            last_feedback = (
                checker_decision.retry_instruction
                or (
                    "The previous result did not satisfy "
                    "the checker criteria."
                )
            )

            EventDispatcher().dispatch(
                "checker.rejected",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )

            EventDispatcher().dispatch(
                "retry.requested",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                attempt=current_attempt + 1,
            )

            current_attempt += 1
            turn = 0

            worker_context = {
                "run_id": run_id,
                "session_id": session_id,
                "workspace_id": workspace_id,
                "principal_id": principal.id,
                "principal_role": principal.role.value,
                "task": task,
                "feedback": last_feedback,
                "observations": [],
                "resuming": False,
            }

            self._save(
                agent_run,
                current_attempt,
                turn,
                worker_context,
                last_feedback,
            )

        agent_run.status = AgentRunStatus.FAILED

        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        raise MaxTurnsReachedError(
            f"Task {run_id} failed after {max_attempts} attempts."
        )

    # ==========================================================================
    # DURABLE STATE
    # ==========================================================================

    @staticmethod
    def _save(
        agent_run: AgentRun,
        current_attempt: int,
        turn: int,
        worker_context: Dict[str, Any],
        last_feedback: Optional[str],
    ) -> None:
        """
        Persist the serializable runtime checkpoint.
        """
        observations: List[Any] = []

        for observation in worker_context.get(
            "observations",
            [],
        ):
            if isinstance(
                observation,
                Observation,
            ):
                observations.append(
                    {
                        "tool_call_id": observation.tool_call_id,
                        "content": observation.content,
                    }
                )
            else:
                observations.append(
                    observation
                )

        persisted_worker_context = {
            "run_id": worker_context.get(
                "run_id"
            ),
            "session_id": worker_context.get(
                "session_id"
            ),
            "workspace_id": worker_context.get(
                "workspace_id"
            ),
            "principal_id": worker_context.get(
                "principal_id"
            ),
            "principal_role": worker_context.get(
                "principal_role"
            ),
            "task": worker_context.get(
                "task"
            ),
            "feedback": worker_context.get(
                "feedback"
            ),
            "resuming": worker_context.get(
                "resuming"
            ),
            "observations": observations,
        }

        agent_run.current_state = {
            "turn": turn,
            "worker_context": persisted_worker_context,
            "last_feedback": last_feedback,
        }

        agent_run.task_attempts = current_attempt
        agent_run.updated_at = datetime.utcnow()

        AgentStateManager.save_agent_run(
            agent_run
        )

    # ==========================================================================
    # NATIVE SUBAGENT CREATION
    # ==========================================================================

    async def spawn_agent(
        self,
        parent_run_id: Optional[str],
        child_run_id: str,
        task: Dict[str, Any],
        role: str,
        budget: float,
        permissions: List[str],
        deadline: Optional[datetime],
        result_schema: Dict[str, Any],
        provider: str = "default",
        model: str = "default",
        session_id: str = "",
        workspace_id: str = "",
        principal: Optional[Principal] = None,
    ) -> Any:
        """
        Create a native subagent with an explicitly bounded capability set.

        Child execution inherits the authenticated Principal and workspace
        rather than creating an implicit system identity.
        """
        del provider

        if principal is None:
            raise PermissionError(
                "Authenticated Principal is required for subagent execution."
            )

        if not isinstance(principal, Principal):
            raise PermissionError(
                "Subagent Principal is invalid."
            )

        if principal.workspace_id != workspace_id:
            raise PermissionError(
                "Principal workspace does not match subagent workspace."
            )

        if budget <= 0:
            raise ValueError(
                "Subagent budget must be greater than zero."
            )

        if not workspace_id:
            raise ValueError(
                "workspace_id is required."
            )

        if not session_id:
            raise ValueError(
                "session_id is required."
            )

        if not child_run_id:
            raise ValueError(
                "child_run_id is required."
            )

        try:
            resource_profile = ResourceManager.allocate(
                task.get(
                    "description",
                    str(task),
                )
            )
        except Exception as exc:
            raise RuntimeError(
                "Unable to allocate resources for subagent execution."
            ) from exc

        runtime_seconds = resource_profile.max_runtime

        if deadline is not None:
            remaining = (
                deadline - datetime.utcnow()
            ).total_seconds()

            runtime_seconds = min(
                runtime_seconds,
                max(
                    0.0,
                    remaining,
                ),
            )

        if runtime_seconds <= 0:
            raise TaskTimeoutError(
                "Subagent deadline does not permit execution."
            )

        capability_set = SubagentCapabilitySet(
            allowed_tools=[],
            allowed_scopes=[],
            max_budget=budget,
            max_runtime=int(runtime_seconds),
            workspace=workspace_id,
            permissions=list(
                permissions
            ),
        )

        adapter = OpenAIAdapter(
            model_name=model
        )

        worker = SubagentFactory.create_subagent(
            role_name=role,
            system_prompt=(
                f"You are a specialized ÆHub subagent for role '{role}'. "
                "Operate strictly within the delegated capability set."
            ),
            tools=[],
            adapter=adapter,
            capabilities=capability_set,
        )

        checker = AgentChecker(
            model_provider=OpenAIAdapter(
                model_name=model
            )
        )

        result = await self.execute_task(
            task=task,
            orchestrator=None,
            worker=worker,
            checker=checker,
            timeout=runtime_seconds,
            run_id=child_run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            principal=principal,
        )

        return {
            "parent_run_id": parent_run_id,
            "child_run_id": child_run_id,
            "role": role,
            "result_schema": result_schema,
            "result": result,
        }


__all__ = [
    "AgentRuntime",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_MAX_TOOL_CALLS",
]