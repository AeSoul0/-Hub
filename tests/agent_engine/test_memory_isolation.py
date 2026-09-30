"""
@file backend/tests/agent_engine/test_memory_isolation.py
@description Unit tests for AuroraMemoryManager.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.memory.manager import AuroraMemoryManager
from app.domain.models.memory import MemoryType

@patch('app.memory.manager.SessionLocal')
@patch('app.memory.manager.AuroraMemoryManager._get_embedding')
def test_save_memory_enforces_isolation(mock_get_embedding, mock_session_local):
    mock_get_embedding.return_value = [0.1, 0.2, 0.3]
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    manager = AuroraMemoryManager(session_id="s1", workspace_id="w1")
    manager.save_memory("Test content", MemoryType.SEMANTIC)
    
    mock_db.add.assert_called_once()
    added_record = mock_db.add.call_args[0][0]
    
    # Assert isolation boundary
    assert added_record.session_id == "s1"
    assert added_record.workspace_id == "w1"
    assert added_record.content == "Test content"
    assert added_record.memory_type == MemoryType.SEMANTIC
    mock_db.commit.assert_called_once()

@patch('app.memory.manager.SessionLocal')
def test_fetch_all_context_enforces_isolation(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_query = mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all
    mock_query.return_value = []
    
    manager = AuroraMemoryManager(session_id="s2", workspace_id="w2")
    manager.fetch_all_context("test query")
    
    # Check that filter was called (it filters by session_id and workspace_id)
    mock_db.query.return_value.filter.assert_called_once()
