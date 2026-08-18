"""
@file tests/integration/test_celery_worker.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.core.celery_app import celery_app, route_to_dlq

@pytest.fixture
def mock_celery_task():
    # A generic celery task mock
    task = MagicMock()
    task.request.id = "test-task-123"
    return task

def test_celery_durable_execution_configuration():
    """M8: Verify that Celery is configured for durable execution (task_acks_late)."""
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True

def test_specialized_worker_pools():
    """M13: Verify that tasks are routed to the correct worker pools (CPU, Browser, LLM)."""
    routes = celery_app.conf.task_routes
    assert 'vision.index_folder' in routes
    assert routes['vision.index_folder']['queue'] == 'cpu_pool'
    
    assert 'browser.extract' in routes
    assert routes['browser.extract']['queue'] == 'browser_pool'

@patch('logging.Logger.error')
def test_dead_letter_queue_routing(mock_logger_error, mock_celery_task):
    """M4/M8: Verify that failed tasks are correctly routed to the DLQ."""
    exc = Exception("Worker crashed unexpectedly")
    
    # Trigger DLQ routing
    route_to_dlq(
        task=mock_celery_task, 
        exc=exc, 
        task_id="test-task-123", 
        args=(), 
        kwargs={}, 
        einfo=None
    )
    
    # Verify the error was logged to the dlq logger
    mock_logger_error.assert_called_once()
    log_msg = mock_logger_error.call_args[0][0]
    assert "Task test-task-123 failed and routed to DLQ" in log_msg
    assert "Worker crashed unexpectedly" in log_msg
