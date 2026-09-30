"""
@file backend/app/budget/manager.py
@description Implements manager.py. Core components: BudgetManager.

This module manages the internal business logic for BudgetManager.
It provides specialized functionality to handle: check_budget.
"""
from typing import Dict

class BudgetManager:
    """
    Represents the BudgetManager entity and its core operations.
    """
    # Dummy storage for budgets
    _budgets: Dict[str, float] = {}

    @classmethod
    async def check_budget(cls, session_id: str, cost: float) -> bool:
        """
        Executes check_budget logic.
        """
        current = cls._budgets.get(session_id, 100.0) # default  budget
        if current >= cost:
            cls._budgets[session_id] = current - cost
            return True
        return False
