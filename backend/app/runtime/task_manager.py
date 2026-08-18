"""
@file backend/app/runtime/task_manager.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.core.database import get_connection


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

class TaskAttempt(BaseModel):
    id: str
    task_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    worker_id: str
    status: TaskState
    error_trace: Optional[str] = None

class TaskStep(BaseModel):
    id: str
    task_attempt_id: str
    step_name: str
    status: TaskState
    started_at: datetime
    finished_at: Optional[datetime] = None
    output_payload: Optional[Dict[str, Any]] = None

class TaskCheckpoint(BaseModel):
    id: str
    task_id: str
    state_snapshot: Dict[str, Any]
    created_at: datetime

class TaskArtifact(BaseModel):
    id: str
    task_id: str
    artifact_type: str
    uri_or_content: str
    created_at: datetime

class Task(BaseModel):
    id: str
    session_id: str
    parent_task_id: Optional[str] = None
    state: TaskState
    payload: Dict[str, Any]
    priority: int = 0
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    version: int = 1
    attempt_number: int = 0
    worker_lease_id: Optional[str] = None
    worker_lease_expires_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None
    cancellation_requested: bool = False
    deadline: Optional[datetime] = None
    max_retries: int = 3

VALID_TRANSITIONS = {
    TaskState.QUEUED: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.RUNNING: {TaskState.WAITING, TaskState.WAITING_APPROVAL, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.RETRYING},
    TaskState.WAITING: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.WAITING_APPROVAL: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.EXPIRED},
    TaskState.RETRYING: {TaskState.QUEUED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.EXPIRED: set()
}

class TaskManager:
    """
    Durable Task Runtime (Phase 2).
    Manages the lifecycle of asynchronous agentic operations, ensuring strict state transitions,
    resiliency, and observability for background workers.
    """
    
    @staticmethod
    def create_task(session_id: str, payload: Dict[str, Any], parent_task_id: Optional[str] = None, priority: int = 0, idempotency_key: Optional[str] = None) -> Task:
        task_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                if idempotency_key:
                    cursor.execute("SELECT id FROM tasks WHERE idempotency_key = %s", (idempotency_key,))
                    row = cursor.fetchone()
                    if row:
                        return TaskManager.get_task(row[0])
                        
                cursor.execute(
                    """
                    INSERT INTO tasks (id, session_id, parent_task_id, state, payload, priority, created_at, updated_at, idempotency_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (task_id, session_id, parent_task_id, TaskState.QUEUED.value, json.dumps(payload), priority, now, now, idempotency_key)
                )
            conn.commit()
            
        return TaskManager.get_task(task_id)
        
    @staticmethod
    def update_state(task_id: str, new_state: TaskState, expected_version: Optional[int] = None, error_message: Optional[str] = None) -> bool:
        task = TaskManager.get_task(task_id)
        if not task:
            return False
            
        if new_state not in VALID_TRANSITIONS.get(task.state, set()):
            raise ValueError(f"Illegal transition: {task.state} -> {new_state}")
            
        version_to_check = expected_version if expected_version is not None else task.version
        if version_to_check != task.version:
            raise ValueError(f"Optimistic locking failed: version mismatch for {task_id}")

        now = datetime.utcnow()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = "UPDATE tasks SET state = %s, updated_at = %s, version = version + 1"
                params = [new_state.value, now]
                
                if error_message:
                    query += ", error_message = %s"
                    params.append(error_message)
                    
                query += " WHERE id = %s AND version = %s"
                params.extend([task_id, task.version])
                
                cursor.execute(query, tuple(params))
                success = cursor.rowcount > 0
            conn.commit()
            return success
            
    @staticmethod
    def acquire_lease(task_id: str, worker_id: str, lease_minutes: int = 5) -> bool:
        from datetime import timedelta
        now = datetime.utcnow()
        task = TaskManager.get_task(task_id)
        if not task or task.state != TaskState.QUEUED:
            return False
            
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks SET worker_lease_id = %s, worker_lease_expires_at = %s, 
                    state = %s, attempt_number = attempt_number + 1, version = version + 1
                    WHERE id = %s AND version = %s
                    """,
                    (worker_id, now + timedelta(minutes=lease_minutes), TaskState.RUNNING.value, task_id, task.version)
                )
                success = cursor.rowcount > 0
            conn.commit()
            return success
            
    @staticmethod
    def get_task(task_id: str) -> Optional[Task]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, session_id, parent_task_id, state, payload, priority, 
                       created_at, updated_at, error_message, version, attempt_number, 
                       worker_lease_id, worker_lease_expires_at, idempotency_key, 
                       cancellation_requested, deadline, max_retries 
                       FROM tasks WHERE id = %s""",
                    (task_id,)
                )
                row = cursor.fetchone()
                
        if not row:
            return None
            
        return Task(
            id=row[0], session_id=row[1], parent_task_id=row[2],
            state=TaskState(row[3]), payload=row[4], priority=row[5],
            created_at=row[6], updated_at=row[7], error_message=row[8],
            version=row[9] if len(row) > 9 else 1,
            attempt_number=row[10] if len(row) > 10 else 0,
            worker_lease_id=row[11] if len(row) > 11 else None,
            worker_lease_expires_at=row[12] if len(row) > 12 else None,
            idempotency_key=row[13] if len(row) > 13 else None,
            cancellation_requested=bool(row[14]) if len(row) > 14 else False,
            deadline=row[15] if len(row) > 15 else None,
            max_retries=row[16] if len(row) > 16 else 3
        )

    @staticmethod
    def renew_lease(task_id: str, worker_id: str, lease_minutes: int = 5) -> bool:
        """Heartbeat mechanism to keep the worker lease alive."""
        from datetime import timedelta
        now = datetime.utcnow()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks SET worker_lease_expires_at = %s, updated_at = %s, version = version + 1
                    WHERE id = %s AND worker_lease_id = %s AND state = %s
                    """,
                    (now + timedelta(minutes=lease_minutes), now, task_id, worker_id, TaskState.RUNNING.value)
                )
                success = cursor.rowcount > 0
            conn.commit()
            return success

    @staticmethod
    def cancel_task(task_id: str) -> bool:
        """Cancellation token mechanism to request task stop."""
        now = datetime.utcnow()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE tasks SET cancellation_requested = TRUE, updated_at = %s, version = version + 1 WHERE id = %s",
                    (now, task_id)
                )
                success = cursor.rowcount > 0
            conn.commit()
            return success

    @staticmethod
    def create_checkpoint(task_id: str, state_snapshot: Dict[str, Any]) -> TaskCheckpoint:
        """Checkpoints mechanism to save agent state for recovery."""
        checkpoint_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO task_checkpoints (id, task_id, state_snapshot, created_at) VALUES (%s, %s, %s, %s)",
                    (checkpoint_id, task_id, json.dumps(state_snapshot), now)
                )
            conn.commit()
            
        return TaskCheckpoint(id=checkpoint_id, task_id=task_id, state_snapshot=state_snapshot, created_at=now)
        
    @staticmethod
    def get_latest_checkpoint(task_id: str) -> Optional[TaskCheckpoint]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, state_snapshot, created_at FROM task_checkpoints WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
                    (task_id,)
                )
                row = cursor.fetchone()
                if row:
                    return TaskCheckpoint(id=row[0], task_id=task_id, state_snapshot=row[1], created_at=row[2])
        return None

    @staticmethod
    def recover_zombie_tasks(timeout_minutes: int = 30):
        """
        Phase 2: Resiliency.
        Finds tasks that have been RUNNING for longer than the timeout and marks them as FAILED.
        Workers that crashed without reporting back leave zombie tasks.
        """
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks 
                    SET state = %s, updated_at = CURRENT_TIMESTAMP, error_message = 'Task timed out (Zombie recovery)'
                    WHERE state = %s AND updated_at < CURRENT_TIMESTAMP - interval '%s minutes'
                    """,
                    (TaskState.FAILED.value, TaskState.RUNNING.value, timeout_minutes)
                )
            conn.commit()
