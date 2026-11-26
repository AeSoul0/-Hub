"""
@file backend/app/agent_engine/runtime.py
@description Native A.U.R.O.R.A. Agent Execution Runtime: the loop.

`AgentRuntime` runs the deterministic Worker -> ToolGateway -> Checker loop;
no agent framework has authority over it. Since Q1 its parts live in their
own modules and the class inherits them:

- runtime_tools.py: the tools a run sees and the execution of a proposal
  through the Tool Gateway;
- runtime_limits.py: capabilities, run limits, spend and the stop of a run,
  plus the live usage the Runs page reads;
- runtime_resume.py: parking a run on an approval and resuming it;
- runtime_state.py: live state events, long-term memory and saving the run;
- runtime_subagents.py: starting a subagent (`spawn_agent`).

This module keeps the loop itself. `_execute_task` reads as the run's
outline, and each step is a method over one `_RunLoop` state:
`_start_run` or `_resume_run`, then for each attempt `_run_attempt` (the
worker's turns, with `_run_proposals` for the tool calls of a turn),
`_end_incomplete_attempt` and `_critic_verdict` (accept, fail, or retry
with `_retry_context`). A step that ends the run returns `_Ended`.

Security invariants enforced here include:

- explicit authenticated Principal;
- persisted run/session/workspace/principal consistency;
- explicit execution run IDs;
- trusted runtime context propagation;
- tool proposal/run consistency;
- durable execution state;
- bounded retries and turns;
- memory context scoped to the authenticated session and workspace;
- model input assembled by the Context Manager (levels L0-L5) inside a
  token budget, with cross-session recall and indexing (M6).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agent_engine.context import ContextManager
from app.agent_engine.delegation import (
    Delegator,
)
from app.agent_engine.control import (
    RunLimits,
    run_interruptible,
    run_registry,
)
from app.agent_engine.errors import (
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
)
from app.agent_engine.routing import Role
from app.agent_engine.state.manager import AgentStateManager
from app.agent_engine.tool_selection import select_tools
from app.core.security import (
    Principal,
    SubagentCapabilitySet,
)
from app.runtime.tool_gateway import ToolGateway
from app.skills.registry import skill_registry
from app.agent_engine.runtime_limits import (
    _ACTIVE_SEGMENTS,
    _LIVE_USAGE,
    LimitsMixin,
    _active_seconds,
    _usd,  # noqa: F401 - re-exported, imported from here before Q1
    live_active_seconds,  # noqa: F401 - re-exported, imported from here before Q1
    live_usage,  # noqa: F401 - re-exported (api/runs.py)
)
from app.agent_engine.resources import ResourceManager  # noqa: F401 - patched as runtime.ResourceManager by tests and evals
from app.agent_engine.runtime_resume import ResumeMixin
from app.agent_engine.runtime_state import StateMixin
from app.agent_engine.runtime_subagents import SubagentsMixin
from app.agent_engine.runtime_tools import ToolsMixin


logger = logging.getLogger(__name__)

# ==============================================================================
# EXECUTION DEFAULTS
# ==============================================================================

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_TOOL_CALLS = 5
DEFAULT_MAX_TOTAL_TOOL_CALLS = 20
# How much of a Critic's instruction the timeline shows (F8).
VERDICT_CHARS = 500















@dataclasses.dataclass
class _RunLoop:
    """
    What changes while one run executes, shared by the parts of
    `_execute_task`: the persisted run, its task and worker context, the
    attempt and turn, the Critic's last feedback, and the current attempt's
    answer.
    """

    agent_run: AgentRun
    task: Dict[str, Any]
    worker_context: Dict[str, Any] = dataclasses.field(default_factory=dict)
    current_attempt: int = 1
    turn: int = 0
    last_feedback: Optional[str] = None
    worker_completed: bool = False
    worker_result: Any = None


@dataclasses.dataclass
class _Ended:
    """A part of the run ended it: `_execute_task` returns `value`."""

    value: Any



# ==============================================================================
# AGENT RUNTIME
# ==============================================================================


class AgentRuntime(ToolsMixin, LimitsMixin, ResumeMixin, StateMixin, SubagentsMixin):
    """
    Native deterministic execution kernel.

    The runtime owns orchestration state while the ToolGateway owns side
    effects and the independent Checker owns acceptance decisions.
    """

    def __init__(
        self,
        db_session: Any = None,
        tool_gateway: Optional[ToolGateway] = None,
        context_manager: Optional[ContextManager] = None,
    ) -> None:
        self.db = db_session
        self.tool_gateway = tool_gateway or ToolGateway()
        self._context_manager = context_manager
        # Set by the AgentEngine: how delegate_task starts a subagent (F8).
        self.delegator: Optional[Delegator] = None

    @property
    def context_manager(self) -> ContextManager:
        # Built on first use so AEHUB_CONTEXT_BUDGET is read at run time.
        if self._context_manager is None:
            self._context_manager = ContextManager()

        return self._context_manager

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
        capabilities: Optional[SubagentCapabilitySet] = None,
        max_cost: Optional[float] = None,
        inherit_untrusted: bool = False,
        parent_run_id: Optional[str] = None,
    ) -> Any:
        """
        Run a task under the kill switch and report its live state.

        `capabilities`, `max_cost`, `inherit_untrusted` and `parent_run_id`
        are set for a subagent: its delegated tools, the budget left by the
        parent run, the parent's untrusted taint and the parent itself.

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
                capabilities=capabilities,
                max_cost=max_cost,
                inherit_untrusted=inherit_untrusted,
                parent_run_id=parent_run_id,
            )
            return result
        finally:
            run_registry.unregister(run_id)
            _ACTIVE_SEGMENTS.pop(run_id, None)
            _LIVE_USAGE.pop(run_id, None)

            waiting = (
                isinstance(result, dict)
                and result.get("status") == "WAITING_APPROVAL"
            )

            await self._emit_state(
                session_id,
                run_id,
                "awaiting_approval" if waiting else "done",
                workspace_id=workspace_id,
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
        capabilities: Optional[SubagentCapabilitySet] = None,
        max_cost: Optional[float] = None,
        inherit_untrusted: bool = False,
        parent_run_id: Optional[str] = None,
    ) -> Any:
        """
        Execute one deterministic Worker -> ToolGateway -> Checker cycle.

        The Principal is mandatory. Existing persisted runs are accepted only
        when their session, workspace and principal identity match the current
        authenticated execution context.
        """
        del orchestrator

        self._check_execution_arguments(
            principal=principal,
            session_id=session_id,
            workspace_id=workspace_id,
            max_attempts=max_attempts,
            max_turns=max_turns,
            max_tool_calls=max_tool_calls,
            max_total_tool_calls=max_total_tool_calls,
        )

        run_id = run_id or str(uuid.uuid4())

        agent_run = AgentStateManager.load_agent_run(
            run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            principal_id=principal.id,
        )

        if agent_run is None:
            started = await self._start_run(
                task=task,
                run_id=run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                principal=principal,
                capabilities=capabilities,
                max_cost=max_cost,
                inherit_untrusted=inherit_untrusted,
                max_attempts=max_attempts,
            )
            loop = _RunLoop(*started)

        else:
            loop = _RunLoop(agent_run=agent_run, task=task)

            ended = await self._resume_run(
                loop,
                principal=principal,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )

            if ended is not None:
                return ended.value

        capability_set = self._capabilities(loop.worker_context)

        model_tools = self._build_model_tools(
            principal,
            capability_set,
            loop.worker_context.get("exposed_tools"),
        )

        limits = self._run_limits(loop.worker_context)

        # Every run has a time limit on active execution unless the caller
        # set its own (or AEHUB_RUN_TIMEOUT_SECONDS=0).
        if timeout is None and limits.max_run_seconds > 0:
            timeout = limits.max_run_seconds

        while loop.current_attempt <= max_attempts:
            ended = await self._run_attempt(
                loop,
                cancellation_token=cancellation_token,
                capability_set=capability_set,
                limits=limits,
                max_tool_calls=max_tool_calls,
                max_total_tool_calls=max_total_tool_calls,
                max_turns=max_turns,
                model_tools=model_tools,
                principal=principal,
                run_id=run_id,
                session_id=session_id,
                timeout=timeout,
                worker=worker,
                workspace_id=workspace_id,
            )

            if ended is not None:
                return ended.value

            ended = self._end_incomplete_attempt(
                loop,
                run_id=run_id,
            )

            if ended is not None:
                return ended.value

            ended = await self._critic_verdict(
                loop,
                cancellation_token=cancellation_token,
                checker=checker,
                limits=limits,
                max_attempts=max_attempts,
                principal=principal,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )

            if ended is not None:
                return ended.value

        loop.agent_run.status = AgentRunStatus.FAILED

        self._save(
            loop.agent_run,
            loop.current_attempt,
            loop.turn,
            loop.worker_context,
            loop.last_feedback,
        )

        raise MaxTurnsReachedError(
            f"Task {run_id} failed after {max_attempts} attempts."
        )

    # ==========================================================================
    # THE PARTS OF ONE RUN (Q1)
    # ==========================================================================

    async def _resume_run(
        self,
        loop: _RunLoop,
        *,
        principal: Principal,
        run_id: str,
        session_id: str,
        workspace_id: str,
    ) -> Optional[_Ended]:
        """
        An existing run: the persisted identity checked against the caller, the
        loop state restored, a terminal run refused, and a run waiting on an
        approval resumed with the decided call.
        Returns _Ended when the run ends here.
        """
        if loop.agent_run.session_id != session_id:
            raise PermissionError(
                "Persisted run session does not match the authenticated session."
            )

        if loop.agent_run.workspace_id != workspace_id:
            raise PermissionError(
                "Persisted run workspace does not match the execution workspace."
            )

        if loop.agent_run.principal_id != principal.id:
            raise PermissionError(
                "Persisted run principal does not match the authenticated Principal."
            )

        loop.current_attempt = max(
            1,
            loop.agent_run.task_attempts,
        )

        current_state = loop.agent_run.current_state or {}

        loop.turn = int(
            current_state.get(
                "turn",
                0,
            )
        )

        loop.worker_context = current_state.get(
            "worker_context"
        ) or {
            "run_id": run_id,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "principal_id": principal.id,
            "principal_role": principal.role.value,
            "task": loop.task,
            "feedback": None,
            "observations": [],
            "resuming": True,
        }

        loop.worker_context["observations"] = [
            observation
            if isinstance(observation, Observation)
            else Observation(**observation)
            for observation in loop.worker_context.get(
                "observations",
                [],
            )
        ]

        loop.worker_context["run_id"] = run_id
        loop.worker_context["session_id"] = session_id
        loop.worker_context["workspace_id"] = workspace_id
        loop.worker_context["principal_id"] = principal.id
        loop.worker_context["principal_role"] = principal.role.value

        loop.last_feedback = current_state.get(
            "last_feedback"
        )

        if loop.agent_run.status == AgentRunStatus.COMPLETED:
            return _Ended(loop.agent_run.result)

        if loop.agent_run.status in {
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.EXPIRED,
        }:
            raise MaxTurnsReachedError(
                f"Task {run_id} cannot resume from terminal state "
                f"{loop.agent_run.status.value}."
            )

        # The persisted task is authoritative on resume: callers that
        # resume after an approval do not resend the original task.
        loop.task = loop.worker_context.get("task") or loop.task

        _ACTIVE_SEGMENTS[run_id] = (
            float(loop.agent_run.usage.get("active_seconds", 0.0)),
            time.monotonic(),
        )
        _LIVE_USAGE[run_id] = loop.agent_run.usage

        if loop.agent_run.status == AgentRunStatus.WAITING_APPROVAL:
            outcome = await self._resume_pending_tool_call(
                agent_run=loop.agent_run,
                worker_context=loop.worker_context,
                principal=principal,
                session_id=session_id,
                workspace_id=workspace_id,
                run_id=run_id,
                current_attempt=loop.current_attempt,
                turn=loop.turn,
                last_feedback=loop.last_feedback,
            )

            if outcome is not None:
                return _Ended(outcome)

        return None

    async def _run_attempt(
        self,
        loop: _RunLoop,
        *,
        cancellation_token: Optional[Any],
        capability_set: SubagentCapabilitySet,
        limits: RunLimits,
        max_tool_calls: int,
        max_total_tool_calls: int,
        max_turns: int,
        model_tools: List[Dict[str, Any]],
        principal: Principal,
        run_id: str,
        session_id: str,
        timeout: Optional[float],
        worker: Any,
        workspace_id: str,
    ) -> Optional[_Ended]:
        """
        One attempt: stop on cancellation or timeout, then the worker's turns,
        each through the spend check, the Context Manager, the model and the
        Tool Gateway, until the worker answers without tool calls or a limit
        ends the attempt.
        Returns _Ended when the run ends here.
        """
        if (
            cancellation_token is not None
            and getattr(
                cancellation_token,
                "is_cancelled",
                False,
            )
        ):
            return _Ended(self._stop_run(
                loop.agent_run,
                RunCancelledError(
                    getattr(cancellation_token, "reason", None)
                    or "Run cancelled."
                ),
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            ))

        if timeout is not None:
            elapsed = _active_seconds(loop.agent_run)

            if elapsed >= timeout:
                loop.agent_run.status = AgentRunStatus.FAILED

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                raise TaskTimeoutError(
                    "Task execution exceeded configured timeout."
                )

        loop.worker_completed = False
        loop.worker_result = None

        while loop.turn < max_turns:
            loop.turn += 1

            loop.worker_context.update(
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
                loop.agent_run,
                principal.id,
                limits,
            )

            if spend_stop is not None:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    spend_stop,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            await self._emit_state(
                session_id,
                run_id,
                "planning",
                workspace_id=workspace_id,
            )

            model_context, context_report = self.context_manager.build(
                loop.worker_context,
                system_prompt=str(
                    worker.full_system_prompt()
                    if hasattr(worker, "full_system_prompt")
                    else getattr(worker, "system_prompt", "") or ""
                ),
            )

            loop.agent_run.usage["context_peak_tokens"] = max(
                int(loop.agent_run.usage.get("context_peak_tokens", 0)),
                context_report.total_tokens,
            )

            try:
                if timeout is not None:
                    elapsed = _active_seconds(loop.agent_run)

                    # Time already spent on tools counts too: past the
                    # limit no further model call starts.
                    if elapsed >= timeout:
                        raise asyncio.TimeoutError()

                    remaining = max(
                        0.1,
                        timeout - elapsed,
                    )

                    step_result = await asyncio.wait_for(
                        run_interruptible(
                            worker.generate(
                                model_context
                            ),
                            cancellation_token,
                        ),
                        timeout=remaining,
                    )
                else:
                    step_result = await run_interruptible(
                        worker.generate(
                            model_context
                        ),
                        cancellation_token,
                    )

            except RunInterrupted as exc:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    exc,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            except asyncio.TimeoutError as exc:
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    "TaskTimeoutError"
                )

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                raise TaskTimeoutError(
                    "Worker execution exceeded configured timeout."
                ) from exc

            except Exception as exc:  # noqa: BLE001 - the run fails with the worker's error recorded
                logger.warning("Worker failed in run %s: %s", run_id, exc)
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    f"Worker failed: {exc}"
                )

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                break

            if not isinstance(step_result, dict):
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    "Worker returned an invalid execution payload."
                )

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                break

            loop.worker_context["resuming"] = False

            usage_stop = self._record_usage(
                loop.agent_run,
                step_result.get("usage"),
                role=str(step_result.get("role") or "worker"),
                principal_id=principal.id,
                limits=limits,
            )

            if usage_stop is not None:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    usage_stop,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            proposals = step_result.get(
                "tool_proposals",
                [],
            )

            if not proposals:
                loop.worker_result = step_result.get(
                    "output"
                )
                loop.worker_completed = True

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                break

            if len(proposals) > max_tool_calls:
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    "Exceeded max tool calls per worker turn."
                )

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                break

            tool_calls_used = int(
                loop.agent_run.usage.get(
                    "tool_calls",
                    0,
                )
            )

            if tool_calls_used + len(proposals) > max_total_tool_calls:
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    "Exceeded max tool calls per run."
                )

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                break

            loop.agent_run.usage["tool_calls"] = (
                tool_calls_used + len(proposals)
            )

            ended = await self._run_proposals(
                loop,
                cancellation_token=cancellation_token,
                capability_set=capability_set,
                limits=limits,
                principal=principal,
                proposals=proposals,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
            )

            if ended is not None:
                return ended

        return None

    async def _run_proposals(
        self,
        loop: _RunLoop,
        *,
        cancellation_token: Optional[Any],
        capability_set: SubagentCapabilitySet,
        limits: RunLimits,
        principal: Principal,
        proposals: List[ToolProposal],
        run_id: str,
        session_id: str,
        workspace_id: str,
    ) -> Optional[_Ended]:
        """
        The tool calls of one worker turn, in order: limits checked before and
        after each, each run through the Tool Gateway, the run saved after
        each. A call that needs an approval parks the run with the rest of
        the turn. Returns _Ended when the run ends here.
        """
        for index, proposal in enumerate(proposals):
            if not isinstance(
                proposal,
                ToolProposal,
            ):
                raise TypeError(
                    "Worker returned an invalid ToolProposal instance."
                )

            if proposal.run_id != run_id:
                loop.agent_run.status = AgentRunStatus.FAILED

                self._save(
                    loop.agent_run,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                )

                raise PermissionError(
                    "Tool proposal run_id does not match the active execution run."
                )

            limit_stop = self._check_before_tool(
                loop.agent_run,
                proposal,
                limits,
            )

            if limit_stop is not None:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    limit_stop,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            await self._emit_state(
                session_id,
                run_id,
                "tool_running",
                workspace_id=workspace_id,
                tool=proposal.tool_name,
            )

            try:
                self._record_observation(
                    loop.worker_context,
                    await run_interruptible(
                        self._execute_proposal(
                            proposal=proposal,
                            principal=principal,
                            session_id=session_id,
                            workspace_id=workspace_id,
                            run_id=run_id,
                            untrusted_context=bool(
                                loop.worker_context.get(
                                    "untrusted_context"
                                )
                            ),
                            capabilities=capability_set,
                            input_channel=self._input_channel(loop.worker_context),
                            exposed_tools=loop.worker_context.get("exposed_tools"),
                            delegation=self._delegation_scope(
                                loop.agent_run,
                                principal,
                                limits,
                                capability_set,
                            ),
                        ),
                        cancellation_token,
                    ),
                )

            except RunInterrupted as exc:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    exc,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            except ApprovalRequiredError as exc:
                # The other calls of the same turn wait in the
                # durable state and run after the decision.
                return _Ended(await self._park(
                    loop.agent_run,
                    loop.worker_context,
                    proposal,
                    exc.approval_id,
                    proposals[index + 1:],
                    loop.current_attempt,
                    loop.turn,
                    loop.last_feedback,
                ))

            limit_stop = self._record_effects(
                loop.agent_run,
                loop.worker_context["observations"][-1],
                limits,
            )

            if limit_stop is not None:
                return _Ended(self._stop_run(
                    loop.agent_run,
                    limit_stop,
                    loop.current_attempt,
                    loop.turn,
                    loop.worker_context,
                    loop.last_feedback,
                ))

            self._save(
                loop.agent_run,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            )

        return None

    def _end_incomplete_attempt(
        self,
        loop: _RunLoop,
        *,
        run_id: str,
    ) -> Optional[_Ended]:
        """
        An attempt that ended without an answer: the run waits on an approval,
        or it fails because the turns ran out.
        Returns _Ended when the run ends here.
        """
        if not loop.worker_completed:
            if (
                loop.agent_run.status
                == AgentRunStatus.WAITING_APPROVAL
            ):
                return _Ended({
                    "status": "WAITING_APPROVAL",
                    "run_id": run_id,
                })

            if loop.agent_run.status != AgentRunStatus.FAILED:
                loop.agent_run.status = AgentRunStatus.FAILED
                loop.agent_run.errors.append(
                    "Maximum turns reached."
                )

            self._save(
                loop.agent_run,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            )

            raise MaxTurnsReachedError(
                f"Task {run_id} failed: maximum turns reached."
            )

        return None

    async def _critic_verdict(
        self,
        loop: _RunLoop,
        *,
        cancellation_token: Optional[Any],
        checker: Any,
        limits: RunLimits,
        max_attempts: int,
        principal: Principal,
        run_id: str,
        session_id: str,
        workspace_id: str,
    ) -> Optional[_Ended]:
        """
        The Critic's verdict on the worker's answer: accepted (guarded, indexed
        in memory, announced), failed for good, or rejected with feedback for
        the next attempt.
        Returns _Ended when the run ends here.
        """
        trace = self.context_manager.fit_trace(
            [
                {
                    "tool_call_id": observation.tool_call_id,
                    "content": observation.content,
                }
                for observation in loop.worker_context.get(
                    "observations",
                    [],
                )
            ]
        )

        spend_stop = self._check_spend(
            loop.agent_run,
            principal.id,
            limits,
        )

        if spend_stop is not None:
            return _Ended(self._stop_run(
                loop.agent_run,
                spend_stop,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            ))

        try:
            checker_decision = await run_interruptible(
                checker.evaluate(
                    task=loop.task,
                    result=loop.worker_result,
                    trace=trace,
                ),
                cancellation_token,
            )

        except RunInterrupted as exc:
            return _Ended(self._stop_run(
                loop.agent_run,
                exc,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            ))

        except Exception as exc:
            loop.agent_run.status = AgentRunStatus.FAILED
            loop.agent_run.errors.append(
                f"Checker failed: {exc}"
            )

            self._save(
                loop.agent_run,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            )

            raise MaxTurnsReachedError(
                f"Task {run_id} failed because the checker "
                "could not produce a trusted decision."
            ) from exc

        usage_stop = self._record_usage(
            loop.agent_run,
            getattr(checker_decision, "usage", None),
            role=Role.CRITIC.value,
            principal_id=principal.id,
            limits=limits,
        )

        if usage_stop is not None:
            return _Ended(self._stop_run(
                loop.agent_run,
                usage_stop,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            ))

        if checker_decision.status == CheckerDecisionEnum.ACCEPT:
            guarded_result = OutputGuardrail.validate(
                str(loop.worker_result)
            )

            loop.agent_run.status = AgentRunStatus.COMPLETED
            loop.agent_run.result = guarded_result
            loop.agent_run.error = None

            await self._index_episode(
                workspace_id=workspace_id,
                principal_id=principal.id,
                session_id=session_id,
                run_id=run_id,
                goal=str(loop.task.get("description", loop.task)),
                result=guarded_result,
                trusted=not loop.worker_context.get("untrusted_context"),
            )

            # The Critic's verdicts in the timeline (F8): which attempt
            # out of how many.
            EventDispatcher().dispatch(
                "checker.accepted",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                attempt=loop.current_attempt,
                details={"max_attempts": max_attempts},
            )

            EventDispatcher().dispatch(
                "run.completed",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                tokens=int(loop.agent_run.usage.get("total_tokens", 0)),
                cost=float(loop.agent_run.usage.get("cost", 0.0)),
            )

            self._save(
                loop.agent_run,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            )

            return _Ended(guarded_result)

        # Not accepted: the draft of this attempt leaves the Nucleo (N1).
        from app.agent_engine.streaming import current_draft

        draft = current_draft()
        if draft is not None:
            await draft.reset()

        if checker_decision.status == CheckerDecisionEnum.FAIL:
            loop.agent_run.status = AgentRunStatus.FAILED
            loop.agent_run.error = (
                checker_decision.retry_instruction
                or "Checker rejected the result as unrecoverable."
            )

            loop.agent_run.errors.append(
                loop.agent_run.error
            )

            EventDispatcher().dispatch(
                "checker.failed",
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                attempt=loop.current_attempt,
                details={
                    "max_attempts": max_attempts,
                    "reason": loop.agent_run.error[:VERDICT_CHARS],
                },
            )

            self._save(
                loop.agent_run,
                loop.current_attempt,
                loop.turn,
                loop.worker_context,
                loop.last_feedback,
            )

            return _Ended(None)

        loop.last_feedback = (
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
            attempt=loop.current_attempt,
            details={
                "max_attempts": max_attempts,
                "retry_instruction": loop.last_feedback[:VERDICT_CHARS],
            },
        )

        EventDispatcher().dispatch(
            "retry.requested",
            run_id=run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            attempt=loop.current_attempt + 1,
            details={"max_attempts": max_attempts},
        )

        loop.current_attempt += 1
        loop.turn = 0

        loop.worker_context = self._retry_context(
            loop.worker_context,
            task=loop.task,
            last_feedback=loop.last_feedback,
            principal=principal,
            session_id=session_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )

        self._save(
            loop.agent_run,
            loop.current_attempt,
            loop.turn,
            loop.worker_context,
            loop.last_feedback,
        )

        return None

    # ==========================================================================
    # START OF A RUN
    # ==========================================================================

    @staticmethod
    def _check_execution_arguments(
        principal: Optional[Principal],
        session_id: str,
        workspace_id: str,
        max_attempts: int,
        max_turns: int,
        max_tool_calls: int,
        max_total_tool_calls: int,
    ) -> None:
        """
        Refuse a run without an authenticated Principal of the execution
        workspace, without a session, or with a limit below one.
        """
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

    async def _start_run(
        self,
        task: Dict[str, Any],
        run_id: str,
        parent_run_id: Optional[str],
        session_id: str,
        workspace_id: str,
        principal: Principal,
        capabilities: Optional[SubagentCapabilitySet],
        max_cost: Optional[float],
        inherit_untrusted: bool,
        max_attempts: int,
    ) -> Tuple[AgentRun, Dict[str, Any], Dict[str, Any], int, int, Optional[str]]:
        """
        A new run: the task through the input guardrail, preferences and
        memories recalled, the tools picked from the task, the run saved and
        announced. Returns the loop's starting state.
        """

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

        preferences, recalled = await self._recall(
            workspace_id=workspace_id,
            principal_id=principal.id,
            query=validated_description,
        )

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
            "preferences": preferences,
            "recalled": recalled,
            "subagent_capabilities": (
                capabilities.model_dump()
                if capabilities is not None
                else None
            ),
            "max_cost": max_cost,
            # A subagent starts tainted when its parent has read
            # untrusted content, and so does a run that recalls an
            # untrusted memory: an injection read in an earlier session
            # (a web page, a document) is back in the prompt.
            "untrusted_context": bool(inherit_untrusted)
            or any(not item.get("trusted", False) for item in recalled),
            # The tools this run may see and call, picked from the
            # user's task alone (never from content read later); None
            # means all of them (M15, ADR-021).
            "exposed_tools": select_tools(
                skill_registry,
                validated_description,
            ),
        }

        last_feedback: Optional[str] = None

        agent_run = AgentRun(
            run_id=run_id,
            # The run tree (F8): a subagent keeps its parent.
            parent_run_id=parent_run_id,
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
            parent_run_id=parent_run_id,
            session_id=session_id,
            workspace_id=workspace_id,
            # Only a role chosen for the command (F8); triage is not shown.
            role=task.get("role"),
            details={"max_attempts": max_attempts},
        )

        _ACTIVE_SEGMENTS[run_id] = (0.0, time.monotonic())
        _LIVE_USAGE[run_id] = agent_run.usage

        return (
            agent_run,
            task,
            worker_context,
            current_attempt,
            turn,
            last_feedback,
        )

    # ==========================================================================
    # RETRY AFTER THE CRITIC
    # ==========================================================================

    @staticmethod
    def _retry_context(
        worker_context: Dict[str, Any],
        task: Dict[str, Any],
        last_feedback: Optional[str],
        principal: Principal,
        session_id: str,
        workspace_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """
        The worker context of the next attempt after a Critic rejection:
        no observations, the Critic's feedback, and what the run keeps
        (preferences, recalled memories, limits, taint, exposed tools).
        """
        return {
            "run_id": run_id,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "principal_id": principal.id,
            "principal_role": principal.role.value,
            "task": task,
            "feedback": last_feedback,
            "observations": [],
            "resuming": False,
            "preferences": worker_context.get("preferences") or [],
            "recalled": worker_context.get("recalled") or [],
            "subagent_capabilities": worker_context.get(
                "subagent_capabilities"
            ),
            "max_cost": worker_context.get("max_cost"),
            # The checker feedback may echo untrusted content, so the
            # taint survives a retry.
            "untrusted_context": bool(
                worker_context.get(
                    "untrusted_context"
                )
            ),
            "exposed_tools": worker_context.get("exposed_tools"),
        }



__all__ = [
    "AgentRuntime",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_MAX_TOTAL_TOOL_CALLS",
]
