"""
@file backend/app/agent_engine/tasks.py
@description Implements tasks.py. Core components: TaskManager.

This module manages the internal business logic for TaskManager.
It provides specialized functionality to handle: register_task, get_task, update_task_status.
"""
from typing import Dict, Any
from app.agent_engine.models import TaskExecution

class TaskManager:
    """
    Represents the TaskManager entity and its core operations.
    """
    """Manages the creation and tracking of tasks within a run."""
    
    def __init__(self):
        """
        Executes __init__ logic.
        """
        # Initialize an empty dictionary to hold active tasks mapped by their ID
        self.active_tasks: Dict[str, TaskExecution] = {}

    def register_task(self, task_execution: TaskExecution) -> None:
        """
        Executes register_task logic.
        """
        # Add a new task execution to the active tasks tracker
        self.active_tasks[task_execution.task_id] = task_execution

    def get_task(self, task_id: str) -> TaskExecution:
        """
        Executes get_task logic.
        """
        # Retrieve a specific task by its ID
        return self.active_tasks.get(task_id)

    def update_task_status(self, task_id: str, status: str, feedback: str = None) -> None:
        """
        Executes update_task_status logic.
        """
        # Update the status and optional feedback for an existing task
        task = self.active_tasks.get(task_id)
        if task:
            task.status = status
            if feedback:
                task.feedback = feedback
