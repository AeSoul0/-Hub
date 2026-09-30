"""
@file backend/tests/agent_engine/test_budget.py
@description Unit tests for the BudgetManager.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.agent_engine.budget import BudgetManager
from app.domain.models.runtime_state import Budget

@patch('app.agent_engine.budget.SessionLocal')
def test_get_budget_creates_if_not_exists(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    budget = BudgetManager.get_budget("user_1")
    
    assert budget.principal_id == "user_1"
    assert budget.max_budget == 10.0
    assert budget.consumed_budget == 0.0
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

@patch('app.agent_engine.budget.SessionLocal')
def test_consume_budget_success(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    existing_budget = Budget(principal_id="user_1", max_budget=10.0, consumed_budget=2.0)
    mock_db.query.return_value.filter.return_value.first.return_value = existing_budget
    
    success = BudgetManager.consume("user_1", 3.0)
    
    assert success is True
    assert existing_budget.consumed_budget == 5.0
    mock_db.commit.assert_called_once()

@patch('app.agent_engine.budget.SessionLocal')
def test_consume_budget_exceeds(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db
    
    existing_budget = Budget(principal_id="user_1", max_budget=10.0, consumed_budget=9.0)
    mock_db.query.return_value.filter.return_value.first.return_value = existing_budget
    
    success = BudgetManager.consume("user_1", 2.0)
    
    assert success is False
    assert existing_budget.consumed_budget == 9.0  # Unchanged
    mock_db.commit.assert_not_called()
