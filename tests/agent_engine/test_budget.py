"""
@file tests/agent_engine/test_budget.py
@description Unit tests for the persistent BudgetManager.

The tests cover budget creation, non-mutating preflight checks, successful
atomic consumption, and overspending rejection.
"""

from unittest.mock import MagicMock, patch

from app.agent_engine.budget import BudgetManager
from app.domain.models.runtime_state import Budget


# ==============================================================================
# TESTS
# ==============================================================================


@patch("app.agent_engine.budget.SessionLocal")
def test_get_budget_creates_if_not_exists(mock_session_local):
    """Create the default principal budget when no record exists."""

    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    (
        mock_db.query.return_value
        .filter.return_value
        .first.return_value
    ) = None

    budget = BudgetManager.get_budget("user_1")

    assert budget.principal_id == "user_1"
    assert budget.max_budget == 10.0
    assert budget.consumed_budget == 0.0

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()


@patch("app.agent_engine.budget.SessionLocal")
def test_available_budget_is_read_only(mock_session_local):
    """Return remaining budget without mutating persistent state."""

    mock_db = MagicMock()

    existing_budget = Budget(
        principal_id="user_1",
        max_budget=10.0,
        consumed_budget=2.0,
    )

    (
        mock_db.query.return_value
        .filter.return_value
        .first.return_value
    ) = existing_budget

    mock_session_local.return_value.__enter__.return_value = mock_db

    available = BudgetManager.available("user_1")

    assert available == 8.0
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


@patch("app.agent_engine.budget.SessionLocal")
def test_check_budget_returns_true_when_affordable(mock_session_local):
    """Approve a budget preflight when enough budget remains."""

    mock_db = MagicMock()

    existing_budget = Budget(
        principal_id="user_1",
        max_budget=10.0,
        consumed_budget=2.0,
    )

    (
        mock_db.query.return_value
        .filter.return_value
        .first.return_value
    ) = existing_budget

    mock_session_local.return_value.__enter__.return_value = mock_db

    assert BudgetManager.check_budget("user_1", 8.0) is True
    assert BudgetManager.check_budget("user_1", 8.01) is False


@patch("app.agent_engine.budget.SessionLocal")
def test_consume_budget_success(mock_session_local):
    """Consume budget atomically when sufficient balance is available."""

    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    existing_budget = Budget(
        principal_id="user_1",
        max_budget=10.0,
        consumed_budget=2.0,
    )

    (
        mock_db.query.return_value
        .filter.return_value
        .with_for_update.return_value
        .first.return_value
    ) = existing_budget

    success = BudgetManager.consume(
        "user_1",
        3.0,
    )

    assert success is True
    assert existing_budget.consumed_budget == 5.0
    mock_db.commit.assert_called_once()


@patch("app.agent_engine.budget.SessionLocal")
def test_consume_budget_exceeds(mock_session_local):
    """Reject consumption that would exceed the principal budget."""

    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    existing_budget = Budget(
        principal_id="user_1",
        max_budget=10.0,
        consumed_budget=9.0,
    )

    (
        mock_db.query.return_value
        .filter.return_value
        .with_for_update.return_value
        .first.return_value
    ) = existing_budget

    success = BudgetManager.consume(
        "user_1",
        2.0,
    )

    assert success is False
    assert existing_budget.consumed_budget == 9.0

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


def test_negative_budget_amount_is_rejected():
    """Reject invalid negative budget amounts before database access."""

    with patch("app.agent_engine.budget.SessionLocal") as mock_session_local:
        try:
            BudgetManager.check_budget(
                "user_1",
                -1.0,
            )
            assert False, "Expected negative budget validation failure"
        except ValueError as exc:
            assert "cannot be negative" in str(exc).lower()

        mock_session_local.assert_not_called()