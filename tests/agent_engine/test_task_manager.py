"""
@file tests/agent_engine/test_task_manager.py
@description Unit tests for the durable TaskManager.

The tests cover task creation, idempotent lookup, lifecycle transitions,
optimistic locking, cancellation requests, checkpoints, and zombie recovery.

All PostgreSQL access is mocked so the suite remains deterministic and fast.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.runtime.task_manager import (
    Task,
    TaskManager,
    TaskState,
)


# ==============================================================================
# TEST FIXTURES
# ==============================================================================


def make_task(
    *,
    task_id="task-1",
    state=TaskState.QUEUED,
    version=1,
) -> Task:
    """Build a complete Task object for isolated unit tests."""
    now = datetime.utcnow()

    return Task(
        id=task_id,
        session_id="session-1",
        state=state,
        payload={
            "tool": "test_tool"
        },
        priority=1,
        created_at=now,
        updated_at=now,
        version=version,
    )


def configure_connection(
    mock_connection,
    *,
    first=None,
    rowcount=1,
    fetchone_sequence=None,
):
    """
    Configure the mocked PostgreSQL connection and cursor contract.
    """
    connection = MagicMock()

    mock_connection.return_value.__enter__.return_value = (
        connection
    )

    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = (
        cursor
    )

    if fetchone_sequence is not None:
        cursor.fetchone.side_effect = (
            fetchone_sequence
        )
    else:
        cursor.fetchone.return_value = first

    cursor.rowcount = rowcount

    return connection, cursor


# ==============================================================================
# CREATION TESTS
# ==============================================================================


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_create_task(
    mock_connection,
):
    """
    Create a new queued task with the canonical ToolGateway contract.
    """
    created_task = make_task()

    connection, cursor = configure_connection(
        mock_connection,
        fetchone_sequence=[
            None,
            (
                created_task.id,
                created_task.session_id,
                created_task.parent_task_id,
                created_task.state.value,
                created_task.payload,
                created_task.priority,
                created_task.created_at,
                created_task.updated_at,
                created_task.error_message,
                created_task.version,
                created_task.attempt_number,
                created_task.worker_lease_id,
                created_task.worker_lease_expires_at,
                created_task.idempotency_key,
                created_task.cancellation_requested,
                created_task.deadline,
                created_task.max_retries,
            ),
        ],
    )

    result = TaskManager.create_task(
        session_id="session-1",
        payload={
            "tool": "test_tool"
        },
        priority=1,
    )

    assert result.session_id == "session-1"
    assert result.state is TaskState.QUEUED
    assert result.payload == {
        "tool": "test_tool"
    }

    assert cursor.execute.call_count == 2
    connection.commit.assert_called_once()


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_create_task_returns_existing_idempotent_task(
    mock_connection,
):
    """
    An existing idempotency key must reuse the stored task.
    """
    existing = make_task(
        task_id="existing-task"
    )

    connection, cursor = configure_connection(
        mock_connection,
        fetchone_sequence=[
            (
                existing.id,
            ),
        ],
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=existing,
    ) as get_task:
        result = TaskManager.create_task(
            session_id="session-1",
            payload={
                "tool": "test_tool"
            },
            idempotency_key="idem-123",
        )

    assert result.id == "existing-task"
    get_task.assert_called_once_with(
        "existing-task"
    )

    cursor.execute.assert_called_once()
    connection.commit.assert_called_once()


# ==============================================================================
# STATE TRANSITION TESTS
# ==============================================================================


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_update_state(
    mock_connection,
):
    """
    Valid state transitions must update the task successfully.
    """
    task = make_task(
        state=TaskState.QUEUED,
        version=1,
    )

    connection, cursor = configure_connection(
        mock_connection,
        rowcount=1,
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=task,
    ):
        result = TaskManager.update_state(
            "task-1",
            TaskState.RUNNING,
        )

    assert result is True
    cursor.execute.assert_called_once()
    connection.commit.assert_called_once()


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_update_state_rejects_illegal_transition(
    mock_connection,
):
    """
    Terminal task states must not transition back into active states.
    """
    task = make_task(
        state=TaskState.COMPLETED
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=task,
    ):
        with pytest.raises(
            ValueError,
            match="Illegal transition",
        ):
            TaskManager.update_state(
                "task-1",
                TaskState.RUNNING,
            )

    mock_connection.assert_not_called()


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_update_state_rejects_version_mismatch(
    mock_connection,
):
    """
    Optimistic locking must reject stale task versions.
    """
    task = make_task(
        state=TaskState.QUEUED,
        version=2,
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=task,
    ):
        with pytest.raises(
            ValueError,
            match="version mismatch",
        ):
            TaskManager.update_state(
                "task-1",
                TaskState.RUNNING,
                expected_version=1,
            )

    mock_connection.assert_not_called()


# ==============================================================================
# CANCELLATION TESTS
# ==============================================================================


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_cancel_task(
    mock_connection,
):
    """
    Cancellation requests must update non-terminal tasks.
    """
    task = make_task(
        state=TaskState.RUNNING
    )

    connection, cursor = configure_connection(
        mock_connection,
        rowcount=1,
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=task,
    ):
        result = TaskManager.cancel_task(
            "task-1"
        )

    assert result is True
    cursor.execute.assert_called_once()
    connection.commit.assert_called_once()


def test_cancel_terminal_task_returns_false():
    """
    Terminal tasks cannot receive another cancellation request.
    """
    task = make_task(
        state=TaskState.COMPLETED
    )

    with patch.object(
        TaskManager,
        "get_task",
        return_value=task,
    ):
        assert (
            TaskManager.cancel_task(
                "task-1"
            )
            is False
        )


# ==============================================================================
# CHECKPOINT TESTS
# ==============================================================================


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_create_checkpoint(
    mock_connection,
):
    """
    Persist a JSON-serializable runtime checkpoint.
    """
    connection, cursor = configure_connection(
        mock_connection
    )

    snapshot = {
        "turn": 2,
        "state": "running",
    }

    checkpoint = TaskManager.create_checkpoint(
        "task-1",
        snapshot,
    )

    assert checkpoint.task_id == "task-1"
    assert checkpoint.state_snapshot == snapshot
    assert checkpoint.id

    cursor.execute.assert_called_once()
    connection.commit.assert_called_once()


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_get_latest_checkpoint(
    mock_connection,
):
    """
    Load the latest checkpoint and decode its state snapshot.
    """
    now = datetime.utcnow()

    connection, cursor = configure_connection(
        mock_connection,
        first=(
            "checkpoint-1",
            {
                "turn": 3,
            },
            now,
        ),
    )

    checkpoint = (
        TaskManager.get_latest_checkpoint(
            "task-1"
        )
    )

    assert checkpoint is not None
    assert checkpoint.id == "checkpoint-1"
    assert checkpoint.task_id == "task-1"
    assert checkpoint.state_snapshot == {
        "turn": 3
    }

    cursor.execute.assert_called_once()


# ==============================================================================
# ZOMBIE RECOVERY TESTS
# ==============================================================================


@patch(
    "app.runtime.task_manager.get_connection"
)
def test_recover_zombie_tasks(
    mock_connection,
):
    """
    Zombie recovery must return the number of affected task records.
    """
    connection, cursor = configure_connection(
        mock_connection,
        rowcount=3,
    )

    affected = (
        TaskManager.recover_zombie_tasks(
            timeout_minutes=30
        )
    )

    assert affected == 3
    cursor.execute.assert_called_once()
    connection.commit.assert_called_once()