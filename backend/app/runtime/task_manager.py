"""
@file backend/app/runtime/task_manager.py
@description Durable task lifecycle manager for A.U.R.O.R.A.

This module manages durable background task records, strict lifecycle
transitions, worker leases, cancellation requests, checkpoints, artifacts,
and zombie-task recovery.

The current Agent Runtime uses this module as a persistence boundary for
individual tool execution tasks. The public API is intentionally small and
framework-agnostic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.core.database import get_connection


# ==============================================================================
# TASK STATE
# ==============================================================================


class TaskState(str, Enum):
    """
    Durable states supported by the task lifecycle.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


VALID_TRANSITIONS = {
    TaskState.QUEUED: {
        TaskState.RUNNING,
        TaskState.CANCELLED,
        TaskState.EXPIRED,
    },
    TaskState.RUNNING: {
        TaskState.WAITING,
        TaskState.WAITING_APPROVAL,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.RETRYING,
    },
    TaskState.WAITING: {
        TaskState.RUNNING,
        TaskState.CANCELLED,
        TaskState.EXPIRED,
    },
    TaskState.WAITING_APPROVAL: {
        TaskState.RUNNING,
        TaskState.CANCELLED,
        TaskState.EXPIRED,
    },
    TaskState.RETRYING: {
        TaskState.QUEUED,
        TaskState.CANCELLED,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.EXPIRED: set(),
}


# ==============================================================================
# TASK DATA CONTRACTS
# ==============================================================================


class TaskAttempt(BaseModel):
    """
    Represents one worker attempt associated with a durable task.
    """

    id: str
    task_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    worker_id: str
    status: TaskState
    error_trace: Optional[str] = None


class TaskStep(BaseModel):
    """
    Represents one logical execution step within a task attempt.
    """

    id: str
    task_attempt_id: str
    step_name: str
    status: TaskState
    started_at: datetime
    finished_at: Optional[datetime] = None
    output_payload: Optional[Dict[str, Any]] = None


class TaskCheckpoint(BaseModel):
    """
    Represents a persisted task checkpoint.
    """

    id: str
    task_id: str
    state_snapshot: Dict[str, Any]
    created_at: datetime


class TaskArtifact(BaseModel):
    """
    Represents a durable task artifact reference or inline payload.
    """

    id: str
    task_id: str
    artifact_type: str
    uri_or_content: str
    created_at: datetime


class Task(BaseModel):
    """
    Complete durable task representation exposed to runtime callers.
    """

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


# ==============================================================================
# TASK MANAGER
# ==============================================================================


class TaskManager:
    """
    Durable task lifecycle manager.

    The manager persists task state through the compatibility PostgreSQL
    connection layer that currently owns the legacy task schema.
    """

    @staticmethod
    def create_task(
        session_id: str,
        payload: Dict[str, Any],
        parent_task_id: Optional[str] = None,
        priority: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> Task:
        """
        Create a durable queued task.

        When an idempotency key already exists, the existing task is returned
        instead of creating another task record.
        """
        if not session_id or not session_id.strip():
            raise ValueError(
                "session_id is required."
            )

        task_id = str(
            uuid.uuid4()
        )

        now = datetime.utcnow()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                if idempotency_key:
                    cursor.execute(
                        """
                        SELECT id
                        FROM tasks
                        WHERE idempotency_key = %s
                        LIMIT 1
                        """,
                        (
                            idempotency_key,
                        ),
                    )

                    row = cursor.fetchone()

                    if row:
                        existing_id = row[0]

                        conn.commit()

                        existing = (
                            TaskManager.get_task(
                                existing_id
                            )
                        )

                        if existing is not None:
                            return existing

                        raise RuntimeError(
                            "Task idempotency record points to a missing task."
                        )

                cursor.execute(
                    """
                    INSERT INTO tasks (
                        id,
                        session_id,
                        parent_task_id,
                        state,
                        payload,
                        priority,
                        created_at,
                        updated_at,
                        idempotency_key
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        task_id,
                        session_id,
                        parent_task_id,
                        TaskState.QUEUED.value,
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            default=str,
                        ),
                        priority,
                        now,
                        now,
                        idempotency_key,
                    ),
                )

            conn.commit()

        task = TaskManager.get_task(
            task_id
        )

        if task is None:
            raise RuntimeError(
                f"Task '{task_id}' was created but could not be reloaded."
            )

        return task

    @staticmethod
    def update_state(
        task_id: str,
        new_state: TaskState,
        expected_version: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Apply one validated lifecycle transition with optimistic locking.
        """
        if not task_id or not task_id.strip():
            raise ValueError(
                "task_id is required."
            )

        task = TaskManager.get_task(
            task_id
        )

        if task is None:
            return False

        allowed_states = VALID_TRANSITIONS.get(
            task.state,
            set(),
        )

        if new_state not in allowed_states:
            raise ValueError(
                f"Illegal transition: "
                f"{task.state} -> {new_state}"
            )

        version_to_check = (
            expected_version
            if expected_version is not None
            else task.version
        )

        if version_to_check != task.version:
            raise ValueError(
                f"Optimistic locking failed: "
                f"version mismatch for {task_id}"
            )

        now = datetime.utcnow()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = (
                    "UPDATE tasks "
                    "SET state = %s, "
                    "updated_at = %s, "
                    "version = version + 1"
                )

                params = [
                    new_state.value,
                    now,
                ]

                if error_message is not None:
                    query += (
                        ", error_message = %s"
                    )
                    params.append(
                        error_message
                    )

                query += (
                    " WHERE id = %s "
                    "AND version = %s"
                )

                params.extend(
                    [
                        task_id,
                        task.version,
                    ]
                )

                cursor.execute(
                    query,
                    tuple(params),
                )

                success = (
                    cursor.rowcount > 0
                )

            conn.commit()

        return success

    @staticmethod
    def acquire_lease(
        task_id: str,
        worker_id: str,
        lease_minutes: int = 5,
    ) -> bool:
        """
        Acquire an exclusive worker lease for a queued task.
        """
        if not worker_id or not worker_id.strip():
            raise ValueError(
                "worker_id is required."
            )

        if lease_minutes <= 0:
            raise ValueError(
                "lease_minutes must be greater than zero."
            )

        now = datetime.utcnow()

        task = TaskManager.get_task(
            task_id
        )

        if (
            task is None
            or task.state != TaskState.QUEUED
        ):
            return False

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET
                        worker_lease_id = %s,
                        worker_lease_expires_at = %s,
                        state = %s,
                        attempt_number = attempt_number + 1,
                        version = version + 1,
                        updated_at = %s
                    WHERE
                        id = %s
                        AND version = %s
                        AND state = %s
                    """,
                    (
                        worker_id,
                        now
                        + timedelta(
                            minutes=lease_minutes
                        ),
                        TaskState.RUNNING.value,
                        now,
                        task_id,
                        task.version,
                        TaskState.QUEUED.value,
                    ),
                )

                success = (
                    cursor.rowcount > 0
                )

            conn.commit()

        return success

    @staticmethod
    def get_task(
        task_id: str,
    ) -> Optional[Task]:
        """
        Load one durable task record.
        """
        if not task_id or not task_id.strip():
            raise ValueError(
                "task_id is required."
            )

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        session_id,
                        parent_task_id,
                        state,
                        payload,
                        priority,
                        created_at,
                        updated_at,
                        error_message,
                        version,
                        attempt_number,
                        worker_lease_id,
                        worker_lease_expires_at,
                        idempotency_key,
                        cancellation_requested,
                        deadline,
                        max_retries
                    FROM tasks
                    WHERE id = %s
                    """,
                    (
                        task_id,
                    ),
                )

                row = cursor.fetchone()

        if not row:
            return None

        payload = row[4]

        if isinstance(
            payload,
            str,
        ):
            payload = json.loads(
                payload
            )

        return Task(
            id=row[0],
            session_id=row[1],
            parent_task_id=row[2],
            state=TaskState(
                row[3]
            ),
            payload=payload,
            priority=row[5],
            created_at=row[6],
            updated_at=row[7],
            error_message=row[8],
            version=row[9],
            attempt_number=row[10],
            worker_lease_id=row[11],
            worker_lease_expires_at=row[12],
            idempotency_key=row[13],
            cancellation_requested=bool(
                row[14]
            ),
            deadline=row[15],
            max_retries=row[16],
        )

    @staticmethod
    def renew_lease(
        task_id: str,
        worker_id: str,
        lease_minutes: int = 5,
    ) -> bool:
        """
        Extend the lease of a task currently owned by a worker.
        """
        if not worker_id or not worker_id.strip():
            raise ValueError(
                "worker_id is required."
            )

        if lease_minutes <= 0:
            raise ValueError(
                "lease_minutes must be greater than zero."
            )

        now = datetime.utcnow()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET
                        worker_lease_expires_at = %s,
                        updated_at = %s,
                        version = version + 1
                    WHERE
                        id = %s
                        AND worker_lease_id = %s
                        AND state = %s
                    """,
                    (
                        now
                        + timedelta(
                            minutes=lease_minutes
                        ),
                        now,
                        task_id,
                        worker_id,
                        TaskState.RUNNING.value,
                    ),
                )

                success = (
                    cursor.rowcount > 0
                )

            conn.commit()

        return success

    @staticmethod
    def cancel_task(
        task_id: str,
    ) -> bool:
        """
        Request cancellation of a non-terminal task.

        The operation is intentionally idempotent: a task that is already
        marked for cancellation is still considered successfully cancelled.
        """
        task = TaskManager.get_task(
            task_id
        )

        if task is None:
            return False

        if task.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.EXPIRED,
        }:
            return False

        now = datetime.utcnow()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET
                        cancellation_requested = TRUE,
                        updated_at = %s,
                        version = version + 1
                    WHERE id = %s
                    """,
                    (
                        now,
                        task_id,
                    ),
                )

                success = (
                    cursor.rowcount > 0
                )

            conn.commit()

        return success

    @staticmethod
    def create_checkpoint(
        task_id: str,
        state_snapshot: Dict[str, Any],
    ) -> TaskCheckpoint:
        """
        Persist a durable task checkpoint.
        """
        if not task_id or not task_id.strip():
            raise ValueError(
                "task_id is required."
            )

        checkpoint_id = str(
            uuid.uuid4()
        )

        now = datetime.utcnow()

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO task_checkpoints (
                        id,
                        task_id,
                        state_snapshot,
                        created_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        checkpoint_id,
                        task_id,
                        json.dumps(
                            state_snapshot,
                            ensure_ascii=False,
                            default=str,
                        ),
                        now,
                    ),
                )

            conn.commit()

        return TaskCheckpoint(
            id=checkpoint_id,
            task_id=task_id,
            state_snapshot=state_snapshot,
            created_at=now,
        )

    @staticmethod
    def get_latest_checkpoint(
        task_id: str,
    ) -> Optional[TaskCheckpoint]:
        """
        Return the newest durable checkpoint for a task.
        """
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        state_snapshot,
                        created_at
                    FROM task_checkpoints
                    WHERE task_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        task_id,
                    ),
                )

                row = cursor.fetchone()

        if not row:
            return None

        snapshot = row[1]

        if isinstance(
            snapshot,
            str,
        ):
            snapshot = json.loads(
                snapshot
            )

        return TaskCheckpoint(
            id=row[0],
            task_id=task_id,
            state_snapshot=snapshot,
            created_at=row[2],
        )

    @staticmethod
    def recover_zombie_tasks(
        timeout_minutes: int = 30,
    ) -> int:
        """
        Mark stale RUNNING tasks as FAILED.

        Uses a parameterized PostgreSQL interval expression so the timeout
        remains a true query parameter instead of being interpolated into SQL.
        """
        if timeout_minutes <= 0:
            raise ValueError(
                "timeout_minutes must be greater than zero."
            )

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET
                        state = %s,
                        updated_at = CURRENT_TIMESTAMP,
                        error_message = %s
                    WHERE
                        state = %s
                        AND updated_at
                            < CURRENT_TIMESTAMP
                            - (%s * INTERVAL '1 minute')
                    """,
                    (
                        TaskState.FAILED.value,
                        "Task timed out during zombie recovery.",
                        TaskState.RUNNING.value,
                        timeout_minutes,
                    ),
                )

                affected_rows = (
                    cursor.rowcount
                )

            conn.commit()

        return affected_rows


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