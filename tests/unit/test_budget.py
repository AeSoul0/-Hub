"""
@file tests/unit/test_budget.py
@description Unit tests for persistent Agent Engine budget management.

The tests mock the shared SQLAlchemy session boundary so budget semantics can
be validated without requiring a live PostgreSQL instance.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agent_engine.budget import BudgetManager
from app.domain.models.runtime_state import Budget


def _mock_session():
    """
    Build a mocked SQLAlchemy session context.
    """
    session = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = session
    context.__exit__.return_value = False

    return context, session


def test_get_budget_creates_missing_budget() -> None:
    """
    Missing principal budgets must be created with deterministic defaults.
    """
    context, db = _mock_session()

    db.query.return_value.filter.return_value.first.return_value = None

    with patch(
        "app.agent_engine.budget.SessionLocal",
        return_value=context,
    ):
        budget = BudgetManager.get_budget("principal-1")

    assert budget.principal_id == "principal-1"
    assert budget.max_budget == 10.0
    assert budget.consumed_budget == 0.0
    assert budget.currency == "USD"

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_check_budget_is_read_only() -> None:
    """
    Checking affordability must not mutate or commit budget state.
    """
    context, db = _mock_session()

    existing = Budget(
        principal_id="principal-1",
        max_budget=10.0,
        consumed_budget=2.0,
        currency="USD",
    )

    db.query.return_value.filter.return_value.first.return_value = existing

    with patch(
        "app.agent_engine.budget.SessionLocal",
        return_value=context,
    ):
        assert BudgetManager.check_budget("principal-1", 3.0) is True

    assert existing.consumed_budget == 2.0
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_consume_budget_success() -> None:
    """
    Successful consumption must debit exactly the requested amount.
    """
    context, db = _mock_session()

    existing = Budget(
        principal_id="principal-1",
        max_budget=10.0,
        consumed_budget=2.0,
        currency="USD",
    )

    (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
        .first.return_value
    ) = existing

    with patch(
        "app.agent_engine.budget.SessionLocal",
        return_value=context,
    ):
        success = BudgetManager.consume(
            "principal-1",
            3.0,
        )

    assert success is True
    assert existing.consumed_budget == 5.0
    db.commit.assert_called_once()


def test_consume_budget_rejects_overspend() -> None:
    """
    Overspending attempts must leave persisted consumption unchanged.
    """
    context, db = _mock_session()

    existing = Budget(
        principal_id="principal-1",
        max_budget=10.0,
        consumed_budget=9.0,
        currency="USD",
    )

    (
        db.query.return_value
        .filter.return_value
        .with_for_update.return_value
        .first.return_value
    ) = existing

    with patch(
        "app.agent_engine.budget.SessionLocal",
        return_value=context,
    ):
        success = BudgetManager.consume(
            "principal-1",
            2.0,
        )

    assert success is False
    assert existing.consumed_budget == 9.0
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_budget_rejects_negative_amount() -> None:
    """
    Negative budget operations must be rejected before mutation.
    """
    with pytest.raises(
        ValueError,
        match="cannot be negative",
    ):
        BudgetManager.consume(
            "principal-1",
            -1.0,
        )