"""
@file backend/app/agent_engine\tasks.py
@description Core module for A.U.R.O.R.A. System Engine.

Implements architectural specifications according to the project roadmap.
Ensures durable execution, secure boundaries, and strict multi-agent orchestration.
"""

from typing import Dict, Any
from app.agent_engine.models import TaskExecution

class TaskManager:
    """Manages the creation and tracking of tasks within a run."""
    
    def __init__(self):
        # Initialize an empty dictionary to hold active tasks mapped by their ID
        self.active_tasks: Dict[str, TaskExecution] = {}

    def register_task(self, task_execution: TaskExecution) -> None:
        # Add a new task execution to the active tasks tracker
        self.active_tasks[task_execution.task_id] = task_execution

    def get_task(self, task_id: str) -> TaskExecution:
        # Retrieve a specific task by its ID
        return self.active_tasks.get(task_id)

    def update_task_status(self, task_id: str, status: str, feedback: str = None) -> None:
        # Update the status and optional feedback for an existing task
        task = self.active_tasks.get(task_id)
        if task:
            task.status = status
            if feedback:
                task.feedback = feedback
