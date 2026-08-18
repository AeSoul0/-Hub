"""
@file backend/app/runtime/task_manager.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import uuid
import json
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
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

class TaskManager:
    """
    Durable Task Runtime (Phase 2).
    Manages the lifecycle of asynchronous agentic operations, ensuring strict state transitions,
    resiliency, and observability for background workers.
    """
    
    @staticmethod
    def create_task(session_id: str, payload: Dict[str, Any], parent_task_id: Optional[str] = None, priority: int = 0) -> Task:
        task_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tasks (id, session_id, parent_task_id, state, payload, priority, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (task_id, session_id, parent_task_id, TaskState.QUEUED.value, json.dumps(payload), priority, now, now)
                )
            conn.commit()
            
        return Task(
            id=task_id, session_id=session_id, parent_task_id=parent_task_id,
            state=TaskState.QUEUED, payload=payload, priority=priority,
            created_at=now, updated_at=now
        )
        
    @staticmethod
    def update_state(task_id: str, new_state: TaskState, error_message: Optional[str] = None):
        now = datetime.utcnow()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                if error_message:
                    cursor.execute(
                        "UPDATE tasks SET state = %s, updated_at = %s, error_message = %s WHERE id = %s",
                        (new_state.value, now, error_message, task_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE tasks SET state = %s, updated_at = %s WHERE id = %s",
                        (new_state.value, now, task_id)
                    )
            conn.commit()
            
    @staticmethod
    def get_task(task_id: str) -> Optional[Task]:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, session_id, parent_task_id, state, payload, priority, created_at, updated_at, error_message FROM tasks WHERE id = %s",
                    (task_id,)
                )
                row = cursor.fetchone()
                
        if not row:
            return None
            
        return Task(
            id=row[0], session_id=row[1], parent_task_id=row[2],
            state=TaskState(row[3]), payload=row[4], priority=row[5],
            created_at=row[6], updated_at=row[7], error_message=row[8]
        )

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
