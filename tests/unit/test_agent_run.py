"""
@file tests/unit/test_agent_run.py
@description Unit tests for native AgentRun lifecycle management.

These tests validate lifecycle semantics independently from the database by
mocking the durable AgentStateManager boundary.
"""

from unittest.mock import patch

import pytest

from app.agent_engine.models import AgentRunStatus
from app.agent_engine.run import RunManager


def test_create_run_returns_unique_queued_run() -> None:
    """
    New runs must start queued and receive unique identifiers.
    """
    manager = RunManager()

    with patch("app.agent_engine.run.AgentStateManager.save_agent_run") as save:
        first = manager.create_run(
            session_id="session-1",
            workspace_id="workspace-1",
        )
        second = manager.create_run(
            session_id="session-1",
            workspace_id="workspace-1",
        )

    assert first.run_id.startswith("run_")
    assert second.run_id.startswith("run_")
    assert first.run_id != second.run_id

    assert first.status is AgentRunStatus.QUEUED
    assert second.status is AgentRunStatus.QUEUED

    assert first.workspace_id == "workspace-1"
    assert first.session_id == "session-1"
    assert save.call_count == 2


def test_run_lifecycle_to_completion() -> None:
    """
    A queued run must transition deterministically to completed.
    """
    manager = RunManager()

    with patch("app.agent_engine.run.AgentStateManager.save_agent_run"):
        run = manager.create_run(
            session_id="session-2",
            workspace_id="workspace-2",
        )

        run = manager.start_run(run)
        assert run.status is AgentRunStatus.RUNNING

        run = manager.complete_run(run, result={"answer": "ok"})

    assert run.status is AgentRunStatus.COMPLETED
    assert run.result == {"answer": "ok"}
    assert run.error is None


def test_terminal_run_cannot_be_cancelled() -> None:
    """
    Terminal runs must reject invalid lifecycle transitions.
    """
    manager = RunManager()

    with patch("app.agent_engine.run.AgentStateManager.save_agent_run"):
        run = manager.create_run(
            session_id="session-3",
            workspace_id="workspace-3",
        )
        run = manager.start_run(run)
        run = manager.complete_run(run, result={"ok": True})

        with pytest.raises(ValueError, match="Cannot cancel a terminal run"):
            manager.cancel_run(run)


def test_fail_run_records_error() -> None:
    """
    Failed runs must retain both the current error and the historical error.
    """
    manager = RunManager()

    with patch("app.agent_engine.run.AgentStateManager.save_agent_run"):
        run = manager.create_run(
            session_id="session-4",
            workspace_id="workspace-4",
        )
        run = manager.start_run(run)
        run = manager.fail_run(run, "worker failure")

    assert run.status is AgentRunStatus.FAILED
    assert run.error == "worker failure"
    assert "worker failure" in run.errors