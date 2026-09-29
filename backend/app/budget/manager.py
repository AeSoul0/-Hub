"""
@file backend/app/budget/manager.py
@description Budget manager.

Implements core logic and architectural definitions.
"""
from typing import Dict

class BudgetManager:
    # Dummy storage for budgets
    _budgets: Dict[str, float] = {}

    @classmethod
    async def check_budget(cls, session_id: str, cost: float) -> bool:
        current = cls._budgets.get(session_id, 100.0) # default  budget
        if current >= cost:
            cls._budgets[session_id] = current - cost
            return True
        return False
