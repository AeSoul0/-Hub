"""
@file backend/app/workflows/engine.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.domain.models.workflow import WorkflowRun, WorkflowState, WorkflowVersion
from app.core.celery_app import secure_task
from app.core.security import Principal

class WorkflowEngine:
    """
    M10 Automation / Workflow Engine.
    Manages execution of versioned workflows with support for checkpoints and human approvals.
    """
    def __init__(self, db: Session):
        self.db = db

    def start_workflow(self, version_id: str, session_id: str, input_data: Dict[str, Any]) -> WorkflowRun:
        """Starts a new workflow run and persists it to the database."""
        version = self.db.query(WorkflowVersion).filter_by(id=version_id).first()
        if not version:
            raise ValueError("Workflow version not found")
            
        run = WorkflowRun(
            workflow_version_id=version_id,
            session_id=session_id,
            status=WorkflowState.QUEUED,
            input_data=input_data,
            state_checkpoint={"variables": input_data, "completed_steps": []}
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        
        # Enqueue the first step execution using Celery (Durable Execution)
        from app.core.celery_app import celery_app
        celery_app.send_task("workflow.execute_step", args=[session_id, run.id])
        return run

    def execute_step(self, run_id: str):
        """
        Executes the current step of a workflow. 
        Usually invoked asynchronously via Celery.
        """
        run = self.db.query(WorkflowRun).filter_by(id=run_id).first()
        if not run or run.status not in [WorkflowState.QUEUED, WorkflowState.RUNNING]:
            return
            
        run.status = WorkflowState.RUNNING
        self.db.commit()
        
        definition = run.version.definition
        steps = definition.get("steps", [])
        
        # Determine next step
        completed = run.state_checkpoint.get("completed_steps", [])
        pending_steps = [s for s in steps if s["id"] not in completed]
        
        if not pending_steps:
            # Workflow finished
            run.status = WorkflowState.COMPLETED
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return
            
        current_step = pending_steps[0]
        run.current_step = current_step["id"]
        self.db.commit()
        
        # Human Approval Check
        if current_step.get("requires_approval", False):
            run.status = WorkflowState.WAITING_APPROVAL
            self.db.commit()
            return # Pause execution until approval
            
        # Execute action (simulate action routing)
        action_type = current_step.get("action")
        try:
            # Simulated execution logic
            result = self._route_action(action_type, current_step, run.state_checkpoint)
            
            # Commit checkpoint
            checkpoint = dict(run.state_checkpoint)
            checkpoint["variables"][f"{current_step['id']}_result"] = result
            checkpoint["completed_steps"].append(current_step["id"])
            run.state_checkpoint = checkpoint
            self.db.commit()
            
            # Trigger next step recursively via Celery
            from app.core.celery_app import celery_app
            celery_app.send_task("workflow.execute_step", args=[run.session_id, run.id])
            
        except Exception as e:
            run.status = WorkflowState.FAILED
            run.output_data = {"error": str(e)}
            run.finished_at = datetime.utcnow()
            self.db.commit()

    def _route_action(self, action_type: str, step_def: dict, state: dict) -> Any:
        """Routes a step to the appropriate executor (Tool, Agent, Script)."""
        if action_type == "agent_task":
            # Here we would normally invoke the agent runtime
            return {"status": "success", "result": "Agent completed task."}
        elif action_type == "tool_call":
            return {"status": "success", "result": "Tool invoked."}
        return {"status": "skipped"}

    def resume_from_approval(self, run_id: str, approved: bool, approved_by: Principal):
        """Resumes a workflow that was paused for human approval."""
        run = self.db.query(WorkflowRun).filter_by(id=run_id).first()
        if not run or run.status != WorkflowState.WAITING_APPROVAL:
            raise ValueError("Run is not waiting for approval")
            
        if not approved:
            run.status = WorkflowState.CANCELLED
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return
            
        # Register approval in state
        checkpoint = dict(run.state_checkpoint)
        checkpoint["completed_steps"].append(run.current_step)
        checkpoint["variables"][f"{run.current_step}_approval"] = f"Approved by {approved_by.id}"
        run.state_checkpoint = checkpoint
        run.status = WorkflowState.RUNNING
        self.db.commit()
        
        # Enqueue next step
        from app.core.celery_app import celery_app
        celery_app.send_task("workflow.execute_step", args=[run.session_id, run.id])
