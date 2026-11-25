"""
@file backend/app/agent_engine/runtime_resume.py
@description Approvals inside a run (part of AgentRuntime, Q1): parking a
run on WAITING_APPROVAL and resuming it with the same run_id after the
decision, without running a tool twice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.errors import (
    ApprovalRequiredError,
)
from app.agent_engine.events import EventDispatcher
from app.agent_engine.models import (
    AgentRun,
    AgentRunStatus,
    ToolProposal,
)
from app.agent_engine.state.manager import AgentStateManager
from app.core.security import (
    Principal,
)


class ResumeMixin:
    """
    Human-in-the-loop for AgentRuntime: park the run with the pending call
    and the rest of its turn, then resume it once the approval is decided.
    """

    async def _park(
        self,
        agent_run: AgentRun,
        worker_context: Dict[str, Any],
        proposal: ToolProposal,
        approval_id: Optional[str],
        queued: List[ToolProposal],
        current_attempt: int,
        turn: int,
        last_feedback: Optional[str],
    ) -> Dict[str, Any]:
        """
        Park a call that needs approval, with the calls of the same turn that
        come after it.

        The parked call is replayed through the ToolGateway on resume and the
        queued ones run after it; the model never sees a placeholder
        observation.
        """
        agent_run.status = AgentRunStatus.WAITING_APPROVAL

        worker_context["pending_tool_call"] = {
            "tool_call_id": proposal.tool_call_id,
            "tool_name": proposal.tool_name,
            "arguments": dict(proposal.arguments),
            "approval_id": approval_id,
        }
        worker_context["queued_tool_calls"] = [
            {
                "tool_call_id": queued_proposal.tool_call_id,
                "tool_name": queued_proposal.tool_name,
                "arguments": dict(queued_proposal.arguments),
            }
            for queued_proposal in queued
        ]

        EventDispatcher().dispatch(
            "tool.approval_required",
            run_id=agent_run.run_id,
            session_id=agent_run.session_id,
            workspace_id=agent_run.workspace_id,
            tool=proposal.tool_name,
            details={
                "approval_id": approval_id,
            },
        )

        # Saved first: whoever reacts to the event reads the parked call.
        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        await self._notify(
            agent_run.session_id,
            "approval.requested",
            {
                "approval_id": approval_id,
                "run_id": agent_run.run_id,
                "tool": proposal.tool_name,
            },
            workspace_id=agent_run.workspace_id,
        )

        return {
            "status": "WAITING_APPROVAL",
            "run_id": agent_run.run_id,
            "approval_id": approval_id,
        }

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
          and neither the tool nor the calls queued after it execute;
        - approved: the exact parked call is replayed through the
          ToolGateway, which re-checks the approval for the same arguments,
          then the calls queued after it run in order (one of them may park
          the run again).

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
            worker_context["queued_tool_calls"] = []
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

        limits = self._run_limits(worker_context)
        capability_set = self._capabilities(worker_context)

        queued = [
            ToolProposal(
                tool_call_id=call["tool_call_id"],
                tool_name=call["tool_name"],
                arguments=call["arguments"],
                run_id=run_id,
            )
            for call in worker_context.get("queued_tool_calls") or []
        ]

        proposals = [
            ToolProposal(
                tool_call_id=pending["tool_call_id"],
                tool_name=pending["tool_name"],
                arguments=pending["arguments"],
                run_id=run_id,
            ),
            *queued,
        ]

        worker_context["pending_tool_call"] = None
        worker_context["queued_tool_calls"] = []

        for index, proposal in enumerate(proposals):
            # The approved call was checked when it was proposed.
            if index > 0:
                limit_stop = self._check_before_tool(
                    agent_run,
                    proposal,
                    limits,
                )

                if limit_stop is not None:
                    return self._stop_run(
                        agent_run,
                        limit_stop,
                        current_attempt,
                        turn,
                        worker_context,
                        last_feedback,
                    )

            try:
                observation = await self._execute_proposal(
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
                    capabilities=capability_set,
                    input_channel=self._input_channel(worker_context),
                    exposed_tools=worker_context.get("exposed_tools"),
                    delegation=self._delegation_scope(
                        agent_run,
                        principal,
                        limits,
                        capability_set,
                    ),
                )

            except ApprovalRequiredError as exc:
                if index == 0:
                    raise

                return await self._park(
                    agent_run,
                    worker_context,
                    proposal,
                    exc.approval_id,
                    proposals[index + 1:],
                    current_attempt,
                    turn,
                    last_feedback,
                )

            self._record_observation(
                worker_context,
                observation,
            )

            limit_stop = self._record_effects(
                agent_run,
                observation,
                limits,
            )

            if limit_stop is not None:
                return self._stop_run(
                    agent_run,
                    limit_stop,
                    current_attempt,
                    turn,
                    worker_context,
                    last_feedback,
                )

        self._save(
            agent_run,
            current_attempt,
            turn,
            worker_context,
            last_feedback,
        )

        return None
