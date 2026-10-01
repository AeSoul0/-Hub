"""
@file backend/app/workflows/engine.py
@description Implements engine.py. Core components: WorkflowEngine.

This module manages the internal business logic for WorkflowEngine.
It provides specialized functionality to handle: start_workflow, execute_step,
_route_action, resume_from_approval.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.security import Principal
from app.domain.models.workflow import (
    WorkflowRun,
    WorkflowState,
    WorkflowVersion,
)


class WorkflowEngine:
    """
    M10 Automation / Workflow Engine.

    Manages execution of versioned workflows with support for checkpoints
    and human approvals.
    """

    def __init__(self, db: Session):
        self.db = db

    def start_workflow(
        self,
        version_id: str,
        session_id: str,
        input_data: Dict[str, Any],
    ) -> WorkflowRun:
        """
        Start a new workflow run and persist it to the database.
        """
        version = (
            self.db
            .query(WorkflowVersion)
            .filter_by(id=version_id)
            .first()
        )

        if not version:
            raise ValueError(
                "Workflow version not found"
            )

        run = WorkflowRun(
            workflow_version_id=version_id,
            session_id=session_id,
            status=WorkflowState.QUEUED,
            input_data=input_data,
            state_checkpoint={
                "variables": input_data,
                "completed_steps": [],
            },
        )

        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        # Enqueue the first step execution using Celery.
        celery_app.send_task(
            "workflow.execute_step",
            args=[session_id, run.id],
        )

        return run

    def execute_step(
        self,
        run_id: str,
    ):
        """
        Execute the current step of a workflow.
        """
        run = (
            self.db
            .query(WorkflowRun)
            .filter_by(id=run_id)
            .first()
        )

        if not run or run.status not in [
            WorkflowState.QUEUED,
            WorkflowState.RUNNING,
        ]:
            return

        run.status = WorkflowState.RUNNING
        self.db.commit()

        definition = run.version.definition
        steps = definition.get("steps", [])

        completed = run.state_checkpoint.get(
            "completed_steps",
            [],
        )

        pending_steps = [
            step
            for step in steps
            if step["id"] not in completed
        ]

        if not pending_steps:
            run.status = WorkflowState.COMPLETED
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return

        current_step = pending_steps[0]
        run.current_step = current_step["id"]
        self.db.commit()

        # Human approval gate.
        if current_step.get(
            "requires_approval",
            False,
        ):
            run.status = WorkflowState.WAITING_APPROVAL
            self.db.commit()
            return

        action_type = current_step.get("action")

        try:
            result = self._route_action(
                action_type,
                current_step,
                run.state_checkpoint,
            )

            checkpoint = dict(
                run.state_checkpoint
            )

            checkpoint["variables"][
                f"{current_step['id']}_result"
            ] = result

            checkpoint["completed_steps"].append(
                current_step["id"]
            )

            run.state_checkpoint = checkpoint
            self.db.commit()

            # Trigger the next step recursively through Celery.
            celery_app.send_task(
                "workflow.execute_step",
                args=[run.session_id, run.id],
            )

        except Exception as exc:
            run.status = WorkflowState.FAILED
            run.output_data = {
                "error": str(exc)
            }
            run.finished_at = datetime.utcnow()
            self.db.commit()

    def _route_action(
        self,
        action_type: str,
        step_def: dict,
        state: dict,
    ) -> Any:
        """
        Route a workflow step to the appropriate executor.
        """
        if action_type == "agent_task":
            return {
                "status": "success",
                "result": "Agent completed task.",
            }

        if action_type == "tool_call":
            return {
                "status": "success",
                "result": "Tool invoked.",
            }

        return {
            "status": "skipped"
        }

    def resume_from_approval(
        self,
        run_id: str,
        approved: bool,
        approved_by: Principal,
    ):
        """
        Resume a workflow that was paused for human approval.
        """
        run = (
            self.db
            .query(WorkflowRun)
            .filter_by(id=run_id)
            .first()
        )

        if (
            not run
            or run.status != WorkflowState.WAITING_APPROVAL
        ):
            raise ValueError(
                "Run is not waiting for approval"
            )

        if not approved:
            run.status = WorkflowState.CANCELLED
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return

        checkpoint = dict(
            run.state_checkpoint
        )

        checkpoint["completed_steps"].append(
            run.current_step
        )

        checkpoint["variables"][
            f"{run.current_step}_approval"
        ] = f"Approved by {approved_by.id}"

        run.state_checkpoint = checkpoint
        run.status = WorkflowState.RUNNING
        self.db.commit()

        celery_app.send_task(
            "workflow.execute_step",
            args=[run.session_id, run.id],
        )