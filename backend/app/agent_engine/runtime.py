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
from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.checker import AgentChecker
from app.agent_engine.control import (
    RunLimits,
    SpendLedger,
    run_interruptible,
    run_registry,
)
from app.agent_engine.errors import (
    BudgetExceededError,
    RunCancelledError,
    RunInterrupted,
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
from app.core.security import (
    BudgetState,
    PolicyEngine,
    Principal,
    SubagentCapabilitySet,
    TaskExecutionContext,
    WorkspacePolicy,
)
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
DEFAULT_MAX_TOTAL_TOOL_CALLS = 20
DEFAULT_TOOL_RUNTIME = 30
DEFAULT_MAX_OUTPUT = 4000
DEFAULT_TOOL_COST = 0.0
NOTIFY_TIMEOUT_SECONDS = 0.5


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
            untrusted_output=cls._is_untrusted_output(metadata),
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
    ) -> List[Dict[str, Any]]:
        """
        Build the function-tool definitions the Worker model may call.

        Only registered tools that the PolicyEngine does not deny for this
        Principal are exposed. Exposure is not authorization: every call
        still goes through the ToolGateway pipeline.
        """
        model_tools: List[Dict[str, Any]] = []

        for tool_name in skill_registry.get_registered_tool_names():
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
                workspace_policy=WorkspacePolicy(),
                budget_state=BudgetState(),
                task_context=TaskExecutionContext(),
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
        max_total_tool_calls: int = DEFAULT_MAX_TOTAL_TOOL_CALLS,
        timeout: Optional[float] = None,
        cancellation_token: Optional[Any] = None,
        run_id: Optional[str] = None,
        session_id: str = "",
        workspace_id: str = "",
        principal: Optional[Principal] = None,
    ) -> Any:
        """
        Run a task under the kill switch and report its live state.

        The run is registered for cancellation (per run or "stop all") for
        as long as it executes; while the global stop is active no new run
        starts.
        """
        run_id = run_id or str(uuid.uuid4())

        if run_registry.halted:
            return {
                "status": "CANCELLED",
                "run_id": run_id,
                "reason": run_registry.halt_reason
                or "Agent runs are stopped.",
            }

        token = run_registry.register(
            run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=getattr(principal, "id", "") or "",
            token=cancellation_token,
        )

        result: Any = None

        try:
            result = await self._execute_task(
                task=task,
                orchestrator=orchestrator,
                worker=worker,
                checker=checker,
                max_attempts=max_attempts,
                max_turns=max_turns,
                max_tool_calls=max_tool_calls,
                max_total_tool_calls=max_total_tool_calls,
                timeout=timeout,
                cancellation_token=token,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal=principal,
            )
            return result
        finally:
            run_registry.unregister(run_id)

            waiting = (
                isinstance(result, dict)
                and result.get("status") == "WAITING_APPROVAL"
            )

            await self._emit_state(
                session_id,
                run_id,
                "awaiting_approval" if waiting else "done",
            )

    async def _execute_task(
        self,
        task: Dict[str, Any],
        orchestrator: Any,
        worker: Any,
        checker: Any,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        max_total_tool_calls: int = DEFAULT_MAX_TOTAL_TOOL_CALLS,
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

        if max_total_tool_calls <= 0:
            raise ValueError(
                "max_total_tool_calls must be greater than zero."
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

            worker_context["observations"] = [
                observation
                if isinstance(observation, Observation)
                else Observation(**observation)
                for observation in worker_context.get(
                    "observations",
                    [],
                )
            ]

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

            # The persisted task is authoritative on resume: callers that
            # resume after an approval do not resend the original task.
            task = worker_context.get("task") or task

            if agent_run.status == AgentRunStatus.WAITING_APPROVAL:
                outcome = await self._resume_pending_tool_call(
                    agent_run=agent_run,
                    worker_context=worker_context,
                    principal=principal,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    run_id=run_id,
                    current_attempt=current_attempt,
                    turn=turn,
                    last_feedback=last_feedback,
                )

                if outcome is not None:
                    return outcome

        model_tools = self._build_model_tools(
            principal
        )

        limits = RunLimits.from_env()

        while current_attempt <= max_attempts:
            if (
                cancellation_token is not None
                and getattr(
                    cancellation_token,
                    "is_cancelled",
                    False,
                )
            ):
                return self._stop_run(
                    agent_run,
                    RunCancelledError(
                        getattr(cancellation_token, "reason", None)
                        or "Run cancelled."
                    ),
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

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
                        "tools": model_tools,
                    }
                )

                spend_stop = self._check_spend(
                    agent_run,
                    principal.id,
                    limits,
                )

                if spend_stop is not None:
                    return self._stop_run(
                        agent_run,
                        spend_stop,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                await self._emit_state(
                    session_id,
                    run_id,
                    "planning",
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
                            run_interruptible(
                                worker.generate(
                                    worker_context
                                ),
                                cancellation_token,
                            ),
                            timeout=remaining,
                        )
                    else:
                        step_result = await run_interruptible(
                            worker.generate(
                                worker_context
                            ),
                            cancellation_token,
                        )

                except RunInterrupted as exc:
                    return self._stop_run(
                        agent_run,
                        exc,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
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

                usage_stop = self._record_usage(
                    agent_run,
                    step_result.get("usage"),
                    role="worker",
                    principal_id=principal.id,
                    limits=limits,
                )

                if usage_stop is not None:
                    return self._stop_run(
                        agent_run,
                        usage_stop,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

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

                tool_calls_used = int(
                    agent_run.usage.get(
                        "tool_calls",
                        0,
                    )
                )

                if tool_calls_used + len(proposals) > max_total_tool_calls:
                    agent_run.status = AgentRunStatus.FAILED
                    agent_run.errors.append(
                        "Exceeded max tool calls per run."
                    )

                    self._save(
                        agent_run,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

                    break

                agent_run.usage["tool_calls"] = (
                    tool_calls_used + len(proposals)
                )

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

                    await self._emit_state(
                        session_id,
                        run_id,
                        "tool_running",
                        tool=proposal.tool_name,
                    )

                    try:
                        self._record_observation(
                            worker_context,
                            await run_interruptible(
                                self._execute_proposal(
                                    proposal=proposal,
                                    principal=principal,
                                    session_id=session_id,
                                    workspace_id=workspace_id,
                                    run_id=run_id,
                                    untrusted_context=bool(
                                        worker_context.get(
                                            "untrusted_context"
                                        )
                                    ),
                                ),
                                cancellation_token,
                            ),
                        )

                    except RunInterrupted as exc:
                        return self._stop_run(
                            agent_run,
                            exc,
                            current_attempt,
                            turn,
                            worker_context,
                            last_feedback,
                        )

                    except ApprovalRequiredError as exc:
                        agent_run.status = (
                            AgentRunStatus.WAITING_APPROVAL
                        )

                        # The call is parked in the durable state and
                        # replayed through the ToolGateway on resume; the
                        # model never sees a placeholder observation.
                        worker_context["pending_tool_call"] = {
                            "tool_call_id": proposal.tool_call_id,
                            "tool_name": proposal.tool_name,
                            "arguments": dict(proposal.arguments),
                            "approval_id": exc.approval_id,
                        }

                        EventDispatcher().dispatch(
                            "tool.approval_required",
                            run_id=run_id,
                            session_id=session_id,
                            workspace_id=workspace_id,
                            tool=proposal.tool_name,
                            details={
                                "approval_id": exc.approval_id,
                            },
                        )

                        await self._notify(
                            session_id,
                            "approval.requested",
                            {
                                "approval_id": exc.approval_id,
                                "run_id": run_id,
                                "tool": proposal.tool_name,
                            },
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
                            "approval_id": exc.approval_id,
                        }

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

            spend_stop = self._check_spend(
                agent_run,
                principal.id,
                limits,
            )

            if spend_stop is not None:
                return self._stop_run(
                    agent_run,
                    spend_stop,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

            try:
                checker_decision = await run_interruptible(
                    checker.evaluate(
                        task=task,
                        result=worker_result,
                        trace=trace,
                    ),
                    cancellation_token,
                )

            except RunInterrupted as exc:
                return self._stop_run(
                    agent_run,
                    exc,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
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

            usage_stop = self._record_usage(
                agent_run,
                getattr(checker_decision, "usage", None),
                role="checker",
                principal_id=principal.id,
                limits=limits,
            )

            if usage_stop is not None:
                return self._stop_run(
                    agent_run,
                    usage_stop,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

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
                    tokens=int(agent_run.usage.get("total_tokens", 0)),
                    cost=float(agent_run.usage.get("cost", 0.0)),
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
                # The checker feedback may echo untrusted content, so the
                # taint survives a retry.
                "untrusted_context": bool(
                    worker_context.get(
                        "untrusted_context"
                    )
                ),
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
    # TOOL PROPOSAL EXECUTION
    # ==========================================================================

    async def _execute_proposal(
        self,
        proposal: ToolProposal,
        principal: Principal,
        session_id: str,
        workspace_id: str,
        run_id: str,
        untrusted_context: bool = False,
    ) -> Observation:
        """
        Run one proposal through the ToolGateway and return its Observation.

        ApprovalRequiredError propagates to the caller; any other failure
        becomes an observation the model can react to.
        """
        trusted = True

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
                return await self._execute_registered_tool(
                    tool=tool,
                    arguments=arguments,
                    session_id=session_id,
                    workspace_id=workspace_id,
                )

            tool_result = await self.tool_gateway.execute(
                invocation,
                executor,
                task_context=TaskExecutionContext(
                    workspace_id=workspace_id,
                    untrusted_context=untrusted_context,
                ),
            )

            content = (
                tool_result.output
                if tool_result.success
                else tool_result.error
            )

        except ApprovalRequiredError:
            raise

        except Exception as exc:
            content = f"Tool execution failed: {exc}"

        return Observation(
            tool_call_id=proposal.tool_call_id,
            tool_name=proposal.tool_name,
            arguments=dict(proposal.arguments),
            content=content,
            trusted=trusted,
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

    async def _resume_pending_tool_call(
        self,
        agent_run: AgentRun,
        worker_context: Dict[str, Any],
        principal: Principal,
        session_id: str,
        workspace_id: str,
        run_id: str,
        current_attempt: int,
        turn: int,
        last_feedback: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve the call parked by a WAITING_APPROVAL run.

        - still pending: the run keeps waiting;
        - denied (explicitly or by timeout): the run is closed as CANCELLED
          and the tool never executes;
        - approved: the exact parked call is replayed through the
          ToolGateway, which re-checks the approval for the same arguments.

        Returns a result to hand back to the caller, or None when the run
        should continue with the next Worker turn.
        """
        pending = worker_context.get(
            "pending_tool_call"
        )

        if not pending:
            agent_run.status = AgentRunStatus.RUNNING
            AgentStateManager.save_agent_run(
                agent_run
            )
            return None

        status = await ApprovalManager.check_approval_status(
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal.id,
            run_id=run_id,
            tool_name=pending["tool_name"],
            arguments=pending["arguments"],
        )

        if status == "WAITING_APPROVAL":
            return {
                "status": "WAITING_APPROVAL",
                "run_id": run_id,
                "approval_id": pending.get("approval_id"),
            }

        if status != "APPROVED":
            worker_context["pending_tool_call"] = None
            agent_run.status = AgentRunStatus.CANCELLED
            agent_run.error = (
                f"Approval for tool '{pending['tool_name']}' was denied."
            )
            agent_run.errors.append(
                agent_run.error
            )

            EventDispatcher().dispatch(
                "run.cancelled",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                tool=pending["tool_name"],
            )

            self._save(
                agent_run,
                current_attempt,
                turn,
                worker_context,
                last_feedback,
            )

            return {
                "status": "DENIED",
                "run_id": run_id,
            }

        agent_run.status = AgentRunStatus.RUNNING

        proposal = ToolProposal(
            tool_call_id=pending["tool_call_id"],
            tool_name=pending["tool_name"],
            arguments=pending["arguments"],
            run_id=run_id,
        )

        self._record_observation(
            worker_context,
            await self._execute_proposal(
                proposal=proposal,
                principal=principal,
                session_id=session_id,
                workspace_id=workspace_id,
                run_id=run_id,
                untrusted_context=bool(
                    worker_context.get(
                        "untrusted_context"
                    )
                ),
            ),
        )
        worker_context["pending_tool_call"] = None

        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        return None

    # ==========================================================================
    # RUN CONTROL: SPEND, STOPS AND LIVE STATE
    # ==========================================================================

    @staticmethod
    def _check_spend(
        agent_run: AgentRun,
        principal_id: str,
        limits: RunLimits,
    ) -> Optional[BudgetExceededError]:
        """
        Refuse the next model call once the run or the month is out of budget.

        The ledger is part of the budget boundary: if it cannot be read the
        call is refused (fail closed).
        """
        run_cost = float(agent_run.usage.get("cost", 0.0))

        if run_cost >= limits.max_run_cost:
            return BudgetExceededError(
                f"Run budget exhausted: {run_cost:.4f} USD of "
                f"{limits.max_run_cost:.2f} USD."
            )

        try:
            month_spent = SpendLedger.spent(principal_id)
        except Exception:
            return BudgetExceededError(
                "Spend ledger unavailable: model calls are blocked."
            )

        if month_spent >= limits.monthly_budget:
            return BudgetExceededError(
                f"Monthly budget exhausted: {month_spent:.4f} USD of "
                f"{limits.monthly_budget:.2f} USD."
            )

        return None

    def _record_usage(
        self,
        agent_run: AgentRun,
        usage: Any,
        role: str,
        principal_id: str,
        limits: RunLimits,
    ) -> Optional[BudgetExceededError]:
        """
        Add one model call to the run totals and the monthly ledger, and
        return a stop when a limit is now reached.
        """
        if not isinstance(usage, dict):
            return None

        totals = agent_run.usage
        model = str(usage.get("model") or "unknown")
        tokens = int(usage.get("total_tokens") or 0)
        cost = float(usage.get("cost") or 0.0)

        totals["model_calls"] = int(totals.get("model_calls", 0)) + 1

        for key in ("input_tokens", "output_tokens", "total_tokens"):
            totals[key] = int(totals.get(key, 0)) + int(usage.get(key) or 0)

        totals["cost"] = round(float(totals.get("cost", 0.0)) + cost, 8)

        if usage.get("estimated"):
            totals["cost_estimated"] = True

        per_model = totals.setdefault("by_model", {}).setdefault(
            model,
            {"calls": 0, "total_tokens": 0, "cost": 0.0},
        )
        per_model["calls"] += 1
        per_model["total_tokens"] += tokens
        per_model["cost"] = round(per_model["cost"] + cost, 8)

        totals.setdefault("calls", []).append(
            {
                "at": datetime.utcnow().isoformat(),
                "role": role,
                "model": model,
                "total_tokens": tokens,
                "cost": cost,
            }
        )

        EventDispatcher().dispatch(
            "model.called",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            tokens=tokens,
            cost=cost,
            model=model,
            role=role,
        )

        try:
            month_spent = SpendLedger.add(principal_id, cost)
        except Exception:
            return BudgetExceededError(
                "Spend ledger unavailable: model calls are blocked."
            )

        if (
            month_spent >= limits.monthly_budget * limits.warning_ratio
            and not totals.get("budget_warning")
        ):
            totals["budget_warning"] = True

            EventDispatcher().dispatch(
                "budget.warning",
                run_id=agent_run.run_id,
                session_id=agent_run.session_id,
                workspace_id=agent_run.workspace_id,
                cost=month_spent,
                details={"monthly_budget": limits.monthly_budget},
            )

        if totals["cost"] >= limits.max_run_cost:
            return BudgetExceededError(
                f"Run budget exhausted: {totals['cost']:.4f} USD of "
                f"{limits.max_run_cost:.2f} USD."
            )

        if month_spent >= limits.monthly_budget:
            return BudgetExceededError(
                f"Monthly budget exhausted: {month_spent:.4f} USD of "
                f"{limits.monthly_budget:.2f} USD."
            )

        return None

    def _stop_run(
        self,
        agent_run: AgentRun,
        reason: RunInterrupted,
        current_attempt: int,
        turn: int,
        worker_context: Dict[str, Any],
        last_feedback: Optional[str],
    ) -> Dict[str, Any]:
        """
        Close a run stopped by the kill switch or a spend limit.
        """
        cancelled = isinstance(reason, RunCancelledError)

        agent_run.status = (
            AgentRunStatus.CANCELLED
            if cancelled
            else AgentRunStatus.FAILED
        )
        agent_run.error = str(reason)
        agent_run.errors.append(agent_run.error)

        EventDispatcher().dispatch(
            "run.cancelled" if cancelled else "budget.exceeded",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            cost=float(agent_run.usage.get("cost", 0.0)),
            details={"reason": agent_run.error},
        )

        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        return {
            "status": "CANCELLED" if cancelled else "BUDGET_EXCEEDED",
            "run_id": agent_run.run_id,
            "reason": agent_run.error,
            "usage": {
                key: agent_run.usage.get(key)
                for key in ("model_calls", "total_tokens", "cost")
            },
        }

    async def _emit_state(
        self,
        session_id: str,
        run_id: str,
        state: str,
        **details: Any,
    ) -> None:
        """
        Publish the live run state (planning / tool_running /
        awaiting_approval / done) to the session.
        """
        await self._notify(
            session_id,
            "run.state",
            {
                "run_id": run_id,
                "state": state,
                **details,
            },
        )

    @staticmethod
    async def _notify(
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Push a realtime event to the session; delivery is best effort and
        never affects execution, nor slows it when the bus is unreachable.
        """
        try:
            from app.core.event_bus import event_bus

            await asyncio.wait_for(
                event_bus.publish(
                    session_id,
                    event_type,
                    data,
                ),
                timeout=NOTIFY_TIMEOUT_SECONDS,
            )
        except Exception:
            pass

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
                        "tool_name": observation.tool_name,
                        "arguments": observation.arguments,
                        "content": observation.content,
                        "trusted": observation.trusted,
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
            "pending_tool_call": worker_context.get(
                "pending_tool_call"
            ),
            "untrusted_context": bool(
                worker_context.get(
                    "untrusted_context"
                )
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
    "DEFAULT_MAX_TOTAL_TOOL_CALLS",
]