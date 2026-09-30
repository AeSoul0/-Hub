"""
@file backend/tests/agent_engine/test_task_manager.py
@description Unit tests for TaskManager.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.runtime.task_manager import TaskManager, TaskState

@pytest.fixture
def manager():
    return TaskManager()

@patch('app.runtime.task_manager.get_connection')
def test_create_task(mock_conn, manager):
    mock_cursor = MagicMock()
    mock_conn.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    task_id = manager.create_task(
        principal_id="p1",
        session_id="s1",
        instruction="Do something",
        priority=10
    )
    
    assert task_id is not None
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

@patch('app.runtime.task_manager.get_connection')
def test_update_state(mock_conn, manager):
    mock_cursor = MagicMock()
    mock_conn.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    manager.update_state("t1", TaskState.RUNNING)
    
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

@patch('app.runtime.task_manager.get_connection')
def test_cancel_task(mock_conn, manager):
    mock_cursor = MagicMock()
    mock_conn.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    manager.cancel_task("t1", "Cancelled by user")
    
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
