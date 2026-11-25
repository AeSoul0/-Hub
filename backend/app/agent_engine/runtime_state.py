"""
@file backend/app/agent_engine/runtime_state.py
@description State of a run (part of AgentRuntime, Q1): live state events,
long-term memory (recall at the start, indexing of accepted runs) and the
durable save of the run after every step.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.agent_engine.models import (
    AgentRun,
    Observation,
)
from app.agent_engine.state.manager import AgentStateManager
from app.memory.store import MemoryKind, MemoryStore, memory_enabled
from app.agent_engine.runtime_limits import _active_seconds


logger = logging.getLogger(__name__)

# Long-term memory recalled into L5 and preferences loaded into L2 at the
# start of a run.
RECALL_LIMIT = 8
PREFERENCE_LIMIT = 30
NOTIFY_TIMEOUT_SECONDS = 0.5


class StateMixin:
    """
    Events, memory and persistence for AgentRuntime.
    """

    async def _emit_state(
        self,
        session_id: str,
        run_id: str,
        state: str,
        workspace_id: str = "",
        **details: Any,
    ) -> None:
        """
        Publish the live run state (planning / tool_running /
        awaiting_approval / done) to the session and its workspace.
        """
        await self._notify(
            session_id,
            "run.state",
            {
                "run_id": run_id,
                "state": state,
                **details,
            },
            workspace_id=workspace_id,
        )

    @staticmethod
    async def _notify(
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
        workspace_id: str = "",
    ) -> None:
        """
        Push a realtime event to the session (and, for control-plane events,
        to its workspace); delivery is best effort and never affects
        execution, nor slows it when the bus is unreachable.
        """
        try:
            from app.core.event_bus import event_bus

            await asyncio.wait_for(
                event_bus.publish(
                    session_id,
                    event_type,
                    data,
                    workspace_id=workspace_id,
                ),
                timeout=NOTIFY_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - realtime events are best effort and never affect a run
            logger.debug("Realtime event %s not delivered: %s", event_type, exc)
            pass

    @staticmethod
    async def _recall(
        workspace_id: str,
        principal_id: str,
        query: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load trusted preferences (L2) and memories relevant to the goal (L5).

        Memory improves a run but is not required for it: any failure is
        logged and the run continues without recall.
        """
        if not memory_enabled():
            return [], []

        def load() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            store = MemoryStore(
                workspace_id=workspace_id,
                principal_id=principal_id,
            )
            preferences = store.preferences(
                limit=PREFERENCE_LIMIT,
            )
            recalled = store.search(
                query,
                limit=RECALL_LIMIT,
                exclude_kinds=[
                    MemoryKind.PREFERENCE.value,
                    MemoryKind.RULE.value,
                ],
            )
            return (
                [hit.to_dict() for hit in preferences],
                [hit.to_dict() for hit in recalled],
            )

        try:
            return await asyncio.to_thread(load)
        except Exception as exc:  # noqa: BLE001 - memory recall is optional for a run
            logger.warning("Memory recall skipped: %s", exc)
            return [], []

    @staticmethod
    async def _index_episode(
        workspace_id: str,
        principal_id: str,
        session_id: str,
        run_id: str,
        goal: str,
        result: Any,
        trusted: bool,
    ) -> None:
        """
        Store an accepted run as an episode for later sessions. A run that
        handled untrusted content is stored as untrusted.
        """
        if not memory_enabled():
            return

        def store() -> None:
            MemoryStore(
                workspace_id=workspace_id,
                principal_id=principal_id,
            ).add(
                f"Task: {goal}\nResult: {result}",
                MemoryKind.EPISODE,
                trusted=trusted,
                source="runtime",
                session_id=session_id,
                run_id=run_id,
            )

        try:
            await asyncio.to_thread(store)
        except Exception as exc:  # noqa: BLE001 - memory indexing is optional for a run
            logger.warning("Memory indexing skipped for run %s: %s", run_id, exc)

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
                        "succeeded": observation.succeeded,
                        "modified_file": observation.modified_file,
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
            "queued_tool_calls": worker_context.get(
                "queued_tool_calls"
            ) or [],
            "subagent_capabilities": worker_context.get(
                "subagent_capabilities"
            ),
            "max_cost": worker_context.get(
                "max_cost"
            ),
            "untrusted_context": bool(
                worker_context.get(
                    "untrusted_context"
                )
            ),
            "exposed_tools": worker_context.get(
                "exposed_tools"
            ),
            "preferences": worker_context.get(
                "preferences"
            ) or [],
            "recalled": worker_context.get(
                "recalled"
            ) or [],
            "observations": observations,
        }

        agent_run.current_state = {
            "turn": turn,
            "worker_context": persisted_worker_context,
            "last_feedback": last_feedback,
        }

        agent_run.task_attempts = current_attempt
        agent_run.updated_at = datetime.utcnow()
        agent_run.usage["active_seconds"] = round(
            _active_seconds(agent_run),
            3,
        )

        AgentStateManager.save_agent_run(
            agent_run
        )
