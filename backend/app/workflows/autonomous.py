"""
@file backend/app/workflows/autonomous.py
@description Native autonomous workflow integration.

This module keeps the autonomous workflow API independent from LangChain and
LangGraph. Workflows invoke the native Aurora compatibility facade and rely on
the Agent Engine for durable execution and validation.
"""

from __future__ import annotations

from app.core.event_bus import event_bus
from app.core.security import Principal, RoleEnum
from app.runtime.aurora import get_aurora_app


# ==============================================================================
# SERVICE PRINCIPAL
# ==============================================================================


BACKGROUND_PRINCIPAL = Principal(
    id="system-workflow",
    role=RoleEnum.SYSTEM,
    workspace_id="system",
)


# ==============================================================================
# WORKFLOW ENGINE
# ==============================================================================


class WorkflowEngine:
    """
    Execute long-running autonomous system workflows.
    """

    @staticmethod
    async def morning_briefing_routine() -> None:
        """
        Generate and publish the autonomous morning briefing.
        """
        session_id = "background_workflow_daemon"

        app = await get_aurora_app()

        initial_state = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Generate a concise morning briefing for the system "
                        "operator. Summarize the most important available "
                        "operational information and return three key points."
                    ),
                }
            ],
            "session_id": session_id,
            "current_intent": "workflow_briefing",
            "principal": BACKGROUND_PRINCIPAL,
        }

        try:
            final_state = await app.ainvoke(
                initial_state,
                config={
                    "configurable": {
                        "run_id": f"workflow:{session_id}",
                    }
                },
            )

            messages = final_state.get(
                "messages",
                [],
            )

            if not messages:
                raise RuntimeError(
                    "Autonomous workflow returned no messages."
                )

            result = getattr(
                messages[-1],
                "content",
                str(messages[-1]),
            )

            await event_bus.publish(
                "global_alerts",
                "notification",
                {
                    "title": "Morning Briefing Ready",
                    "content": result,
                },
            )

        except Exception as exc:
            await event_bus.publish(
                "global_alerts",
                "error",
                {
                    "title": "Morning Briefing Failed",
                    "content": str(exc),
                },
            )
            raise

    @staticmethod
    def register_workflows() -> None:
        """
        Register autonomous workflows with the application scheduler.

        The scheduler integration remains explicit so importing this module
        cannot silently start background jobs.
        """
        return


# ==============================================================================
# PUBLIC COMPATIBILITY ENTRYPOINT
# ==============================================================================


def register_workflows() -> None:
    """
    Public compatibility entrypoint used by application startup.
    """
    WorkflowEngine.register_workflows()


__all__ = [
    "BACKGROUND_PRINCIPAL",
    "WorkflowEngine",
    "register_workflows",
]