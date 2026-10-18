"""
@file backend/app/agent_engine/tasks.py
@description Compatibility facade for the canonical runtime TaskManager.

The Agent Engine previously contained a second in-memory TaskManager
implementation. That implementation is intentionally removed because task
durability and lifecycle belong to the Runtime layer.

Canonical ownership:
    app.runtime.task_manager.TaskManager

This module remains temporarily available to avoid breaking existing imports.
New code must import TaskManager directly from app.runtime.task_manager.

Migration policy:
- Existing imports remain functional.
- No task lifecycle logic is implemented here.
- No in-memory task registry is maintained here.
- Future cleanup may remove this compatibility module entirely once all
  external references have been migrated.
"""

from app.runtime.task_manager import (
    Task,
    TaskAttempt,
    TaskArtifact,
    TaskCheckpoint,
    TaskManager,
    TaskState,
    TaskStep,
    VALID_TRANSITIONS,
)


__all__ = [
    "Task",
    "TaskAttempt",
    "TaskArtifact",
    "TaskCheckpoint",
    "TaskManager",
    "TaskState",
    "TaskStep",
    "VALID_TRANSITIONS",
]