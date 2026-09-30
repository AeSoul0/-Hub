"""
@file backend/app/budget/manager.py
@description Compatibility facade for the canonical Agent Engine budget service.

All budget authority is implemented by app.agent_engine.budget.BudgetManager.
This module exists only to preserve the import path used by legacy runtime
components while preventing a second in-memory or session-scoped budget store.

The facade exposes synchronous and asynchronous-compatible methods for older
callers without introducing a second budget implementation.
"""

from __future__ import annotations

from app.agent_engine.budget import BudgetManager as _BudgetManager


class BudgetManager:
    """
    Compatibility facade over the canonical persistent BudgetManager.
    """

    @classmethod
    def get_budget(cls, principal_id: str):
        """
        Return the persistent budget for a principal.
        """
        return _BudgetManager.get_budget(principal_id)

    @classmethod
    def available(cls, principal_id: str) -> float:
        """
        Return the remaining persistent budget.
        """
        return _BudgetManager.available(principal_id)

    @classmethod
    async def check_budget(
        cls,
        principal_id: str,
        amount: float,
    ) -> bool:
        """
        Async compatibility wrapper for read-only budget checks.

        This method never consumes budget.
        """
        return _BudgetManager.check_budget(
            principal_id,
            amount,
        )

    @classmethod
    def consume(
        cls,
        principal_id: str,
        amount: float,
    ) -> bool:
        """
        Consume budget through the canonical persistent implementation.
        """
        return _BudgetManager.consume(
            principal_id,
            amount,
        )


__all__ = ["BudgetManager"]