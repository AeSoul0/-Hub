"""
@file backend/tests/agent_engine/test_idempotency.py
@description Unit tests for IdempotencyManager.
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.agent_engine.state.idempotency import IdempotencyManager
from app.domain.models.runtime_state import IdempotencyKey

@patch('app.agent_engine.state.idempotency.SessionLocal')
def test_save_result_new_key(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    IdempotencyManager.save_result("key_123", {"status": "ok"})
    
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

@patch('app.agent_engine.state.idempotency.SessionLocal')
def test_get_result_valid(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    record = IdempotencyKey(key="key_123", result='{"status": "ok"}', expires_at=datetime.utcnow() + timedelta(days=1))
    mock_db.query.return_value.filter.return_value.first.return_value = record
    
    result = IdempotencyManager.get_result("key_123")
    
    assert result == {"status": "ok"}

@patch('app.agent_engine.state.idempotency.SessionLocal')
def test_get_result_expired(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    record = IdempotencyKey(key="key_123", result='{"status": "ok"}', expires_at=datetime.utcnow() - timedelta(days=1))
    mock_db.query.return_value.filter.return_value.first.return_value = record
    
    result = IdempotencyManager.get_result("key_123")
    
    assert result is None
    mock_db.delete.assert_called_once_with(record)
    mock_db.commit.assert_called_once()
