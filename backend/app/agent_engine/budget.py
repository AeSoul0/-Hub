"""
@file backend/app/agent_engine/budget.py
@description Implements budget.py. Core components: BudgetManager.

This module manages the internal business logic for BudgetManager.
It provides specialized functionality to handle: get_budget, consume.
"""
from app.core.db import SessionLocal
from app.domain.models.runtime_state import Budget

class BudgetManager:
    """
    Represents the BudgetManager entity and its core operations.
    """
    @classmethod
    def get_budget(cls, principal_id: str) -> Budget:
        """
        Executes get_budget logic.
        """
        with SessionLocal() as db:
            record = db.query(Budget).filter(Budget.principal_id == principal_id).first()
            if not record:
                record = Budget(principal_id=principal_id, max_budget=10.0, consumed_budget=0.0)
                db.add(record)
                db.commit()
                db.refresh(record)
            return record

    @classmethod
    def consume(cls, principal_id: str, amount: float) -> bool:
        """
        Executes consume logic.
        """
        with SessionLocal() as db:
            record = db.query(Budget).filter(Budget.principal_id == principal_id).first()
            if not record:
                record = Budget(principal_id=principal_id, max_budget=10.0, consumed_budget=0.0)
                db.add(record)
                
            if record.consumed_budget + amount > record.max_budget:
                return False
                
            record.consumed_budget += amount
            db.commit()
            return True
