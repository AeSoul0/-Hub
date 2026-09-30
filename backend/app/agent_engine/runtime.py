"""
@file backend/app/agent_engine/runtime.py
@description Native A.U.R.O.R.A. Agent Execution Runtime.

Implements the deterministic Worker -> ToolGateway -> Checker -> Retry loop
without relying on LangGraph. The runtime resolves registered tools through
the SkillRegistry, builds strict ToolInvocation boundaries, persists durable
run state, handles approval pauses, and enforces global execution limits.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.agent_engine.adapters.base import ModelProvider
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
from app.core.security import Principal, SubagentCapabilitySet
from app.skills.registry import skill_registry
from app.runtime.tool_gateway import ToolGateway, ToolInvocation


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

    The runtime owns orchestration state but delegates all side effects to the
    ToolGateway and all acceptance decisions to the independent Checker.
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
        Resolves a registered tool callable and its metadata.

        Unknown tools are rejected before any execution occurs.
        """
        metadata = skill_registry._tool_metadata.get(tool_name)

        if metadata is None:
            raise ValueError(
                f"Tool '{tool_name}' is not registered in SkillRegistry."
            )

        for tool in skill_registry.get_all_tools():
            candidate_name = getattr(tool, "name", None) or getattr(
                tool,
                "__name__",
                None,
            )

            if candidate_name == tool_name:
                return tool, metadata

        raise ValueError(
            f"Tool '{tool_name}' has metadata but no executable implementation."
        )

    @classmethod
    def _build_tool_spec(cls, tool_name: str) -> ToolSpec:
        """
        Converts the existing skill metadata contract into the stricter
        ToolSpec required by the ToolGateway.

        Conservative defaults are used for capabilities that legacy skill
        metadata does not currently expose.
        """
        _, metadata = cls._resolve_tool(tool_name)

        risk_level = str(metadata.risk_level.value).upper()

        return ToolSpec(
            name=metadata.name,
            version="1.0.0",
            description=metadata.description,
            input_schema={},
            output_schema={},
            risk_level=risk_level,
            permissions=list(metadata.permissions_required),
            network_access=False,
            filesystem_access=False,
            max_runtime=DEFAULT_TOOL_RUNTIME,
            max_output=DEFAULT_MAX_OUTPUT,
            max_cost=DEFAULT_TOOL_COST,
            idempotent=False,
            requires_approval=metadata.requires_approval,
            sandbox_profile="default",
            audit_policy="standard",
        )

    @staticmethod
    async def _execute_registered_tool(tool: Any, arguments: Dict[str, Any]) -> Any:
        """
        Executes a registered sync or async tool implementation.

        Supports LangChain-style structured tools exposing an `ainvoke`
        method, normal async callables, and regular synchronous callables.
        """
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(arguments)

        if inspect.iscoroutinefunction(tool):
            return await tool(**arguments)

        return await asyncio.to_thread(tool, **arguments)

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
        session_id: str = "default_session",
        workspace_id: str = "default_workspace",
        principal: Optional[Principal] = None,
    ) -> Any:
        """
        Executes one deterministic Worker -> ToolGateway -> Checker cycle.

        Returns the final guarded worker output or a WAITING_APPROVAL payload.
        """
        run_id = run_id or str(uuid.uuid4())

        principal = principal or Principal(
            id=session_id,
            role="user",
            workspace_id=workspace_id,
        )

        if principal.workspace_id != workspace_id:
            raise PermissionError(
                "Principal workspace does not match execution workspace."
            )

        agent_run = AgentStateManager.load_agent_run(run_id)

        if agent_run is None:
            start_time = datetime.utcnow()
            current_attempt = 1
            turn = 0

            validated_description = InputGuardrail.validate(
                str(task.get("description", task))
            )

            task = {**task, "description": validated_description}
            worker_context: Dict[str, Any] = {
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
                status=AgentRunStatus.RUNNING,
                task_attempts=current_attempt,
                current_state={
                    "turn": turn,
                    "worker_context": worker_context,
                    "last_feedback": last_feedback,
                },
                created_at=start_time,
            )

            AgentStateManager.save_agent_run(agent_run)
            EventDispatcher().dispatch(
                "run.started",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )
        else:
            start_time = agent_run.created_at
            current_attempt = max(1, agent_run.task_attempts)
            current_state = agent_run.current_state or {}
            turn = int(current_state.get("turn", 0))
            worker_context = current_state.get("worker_context") or {
                "task": task,
                "feedback": None,
                "observations": [],
                "resuming": True,
            }
            last_feedback = current_state.get("last_feedback")

            if agent_run.status == AgentRunStatus.WAITING_APPROVAL:
                agent_run.status = AgentRunStatus.RUNNING
                AgentStateManager.save_agent_run(agent_run)

        while current_attempt <= max_attempts:
            if (
                cancellation_token is not None
                and getattr(cancellation_token, "is_cancelled", False)
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
                elapsed = (datetime.utcnow() - start_time).total_seconds()
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

                try:
                    if timeout is not None:
                        elapsed = (
                            datetime.utcnow() - start_time
                        ).total_seconds()
                        remaining = max(0.1, timeout - elapsed)
                        step_result = await asyncio.wait_for(
                            worker.generate(worker_context),
                            timeout=remaining,
                        )
                    else:
                        step_result = await worker.generate(worker_context)
                except asyncio.TimeoutError as exc:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append("TaskTimeoutError")
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
                    agent_run.errors.append(f"Worker failed: {exc}")
                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )
                    break

                worker_context["resuming"] = False
                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

                proposals = step_result.get("tool_proposals", [])

                if not proposals:
                    worker_result = step_result.get("output")
                    worker_completed = True
                    break

                if len(proposals) > max_tool_calls:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "Exceeded max tool calls per turn."
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
                    if not isinstance(proposal, ToolProposal):
                        raise TypeError(
                            "Worker returned an invalid ToolProposal instance."
                        )

                    try:
                        tool, _ = self._resolve_tool(proposal.tool_name)
                        spec = self._build_tool_spec(proposal.tool_name)

                        invocation = ToolInvocation(
                            tool_name=proposal.tool_name,
                            arguments=dict(proposal.arguments),
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

                        async def executor(**arguments: Any) -> Any:
                            return await self._execute_registered_tool(
                                tool,
                                arguments,
                            )

                        tool_result = await self.tool_gateway.execute(
                            invocation,
                            executor,
                        )

                        worker_context["observations"].append(
                            Observation(
                                tool_call_id=proposal.tool_call_id,
                                content=tool_result.output
                                if tool_result.success
                                else tool_result.error,
                            )
                        )

                    except ApprovalRequiredError:
                        agent_run.status = AgentRunStatus.WAITING_APPROVAL

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
                                content="Waiting for human approval.",
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
                                content=f"Tool execution failed: {exc}",
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
                if agent_run.status == AgentRunStatus.WAITING_APPROVAL:
                    return {
                        "status": "WAITING_APPROVAL",
                        "run_id": run_id,
                    }

                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append("Maximum turns reached.")
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

            # The full observation trace is passed to the independent checker.
            trace = [
                {
                    "tool_call_id": observation.tool_call_id,
                    "content": observation.content,
                }
                for observation in worker_context.get("observations", [])
            ]

            try:
                checker_decision = await checker.evaluate(
                    task=task,
                    result=worker_result,
                    trace=trace,
                )
            except Exception as exc:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.errors.append(f"Checker failed: {exc}")
                self._save(
                    agent_run,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )
                raise

            if checker_decision.status == CheckerDecisionEnum.ACCEPT:
                guarded_result = OutputGuardrail.validate(
                    str(worker_result)
                )

                agent_run.status = AgentRunStatus.COMPLETED

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
                agent_run.errors.append(
                    checker_decision.retry_instruction
                    or "Checker rejected the result as unrecoverable."
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
                or "The previous result did not satisfy the checker criteria."
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
        Persists the serializable execution checkpoint.
        """
        observations = []

        for observation in worker_context.get("observations", []):
            if isinstance(observation, Observation):
                observations.append(
                    {
                        "tool_call_id": observation.tool_call_id,
                        "content": observation.content,
                    }
                )
            else:
                observations.append(observation)

        agent_run.current_state = {
            "turn": turn,
            "worker_context": {
                "task": worker_context.get("task"),
                "feedback": worker_context.get("feedback"),
                "resuming": worker_context.get("resuming"),
                "observations": observations,
            },
            "last_feedback": last_feedback,
        }
        agent_run.task_attempts = current_attempt
        agent_run.updated_at = datetime.utcnow()

        AgentStateManager.save_agent_run(agent_run)

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
        session_id: str = "default_session",
        workspace_id: str = "default_workspace",
    ) -> Any:
        """
        Creates a native subagent with an explicitly bounded capability set.

        No LangGraph graph is created or invoked here.
        """
        from app.agents.subagents.base import SubagentFactory
        from app.agent_engine.adapters.openai_adapter import OpenAIAdapter

        if budget <= 0:
            raise ValueError("Subagent budget must be greater than zero.")

        if not workspace_id:
            raise ValueError("workspace_id is required.")

        try:
            resource_profile = ResourceManager.allocate(
                task.get("description", str(task))
            )
        except Exception as exc:
            raise RuntimeError(
                "Unable to allocate resources for subagent execution."
            ) from exc

        runtime_seconds = resource_profile.max_runtime

        if deadline is not None:
            remaining = (deadline - datetime.utcnow()).total_seconds()
            runtime_seconds = min(runtime_seconds, max(0.0, remaining))

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
            permissions=list(permissions),
        )

        adapter = OpenAIAdapter(model_name=model)
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
            model_provider=OpenAIAdapter(model_name=model)
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
        )

        return {
            "parent_run_id": parent_run_id,
            "child_run_id": child_run_id,
            "role": role,
            "result_schema": result_schema,
            "result": result,
        }
