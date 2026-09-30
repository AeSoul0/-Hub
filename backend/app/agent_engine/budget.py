"""
@file backend/app/agent_engine/budget.py
@description Persistent budget management for the native Agent Engine.

This module provides the single source of truth for principal-level runtime
budgets. Budget state is persisted in PostgreSQL through the shared SQLAlchemy
session factory.

Important invariants:
- Budget state is keyed by principal identity, never by transient session ID.
- Checking available budget is read-only.
- Consuming budget is an atomic database transaction.
- A rejected consumption never changes persisted usage.
"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.domain.models.runtime_state import Budget


DEFAULT_MAX_BUDGET = 10.0
DEFAULT_CURRENCY = "USD"


class BudgetManager:
    """
    Manage persistent principal-level execution budgets.
    """

    @classmethod
    def get_budget(cls, principal_id: str) -> Budget:
        """
        Load or create the budget belonging to one principal.
        """
        cls._validate_principal(principal_id)

        with SessionLocal() as db:
            record = (
                db.query(Budget)
                .filter(Budget.principal_id == principal_id)
                .first()
            )

            if record is None:
                record = Budget(
                    principal_id=principal_id,
                    max_budget=DEFAULT_MAX_BUDGET,
                    consumed_budget=0.0,
                    currency=DEFAULT_CURRENCY,
                )
                db.add(record)
                db.commit()
                db.refresh(record)

            return record

    @classmethod
    def available(cls, principal_id: str) -> float:
        """
        Return the currently available budget without mutating state.
        """
        budget = cls.get_budget(principal_id)

        return max(
            0.0,
            float(budget.max_budget) - float(budget.consumed_budget),
        )

    @classmethod
    def check_budget(cls, principal_id: str, amount: float) -> bool:
        """
        Check whether an amount can be afforded without consuming it.

        The actual debit must happen only after policy and approval checks
        have completed successfully.
        """
        cls._validate_amount(amount)

        return cls.available(principal_id) >= amount

    @classmethod
    def consume(cls, principal_id: str, amount: float) -> bool:
        """
        Atomically consume budget for a principal.

        Row-level locking prevents concurrent executions from overspending
        the same principal budget.
        """
        cls._validate_principal(principal_id)
        cls._validate_amount(amount)

        if amount == 0:
            return True

        with SessionLocal() as db:
            record = (
                db.query(Budget)
                .filter(Budget.principal_id == principal_id)
                .with_for_update()
                .first()
            )

            if record is None:
                record = Budget(
                    principal_id=principal_id,
                    max_budget=DEFAULT_MAX_BUDGET,
                    consumed_budget=0.0,
                    currency=DEFAULT_CURRENCY,
                )
                db.add(record)
                db.flush()

            next_consumed = float(record.consumed_budget) + amount

            if next_consumed > float(record.max_budget):
                db.rollback()
                return False

            record.consumed_budget = next_consumed
            db.commit()

            return True

    @staticmethod
    def _validate_principal(principal_id: str) -> None:
        """
        Reject missing principal identities instead of creating shared budgets.
        """
        if not principal_id or not principal_id.strip():
            raise ValueError("principal_id is required")

    @staticmethod
    def _validate_amount(amount: float) -> None:
        """
        Validate a budget amount before database access.
        """
        if amount < 0:
            raise ValueError("Budget amount cannot be negative")