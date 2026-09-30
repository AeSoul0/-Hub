"""
@file backend/app/domain/models/runtime_state.py
@description Implements runtime_state.py. Core components: AgentRun, IdempotencyKey, Budget.

This module manages the internal business logic for AgentRun, IdempotencyKey, Budget.
It provides specialized functionality to handle: persistence of runtime states.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, Float

from app.domain.models.identity import Base

class AgentRun(Base):
    """
    Represents the AgentRun entity and its core operations.
    """
    __tablename__ = "agent_runs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    principal_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    input_data = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="running")
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class IdempotencyKey(Base):
    """
    Represents the IdempotencyKey entity and its core operations.
    """
    __tablename__ = "idempotency_keys"
    
    key = Column(String, primary_key=True)
    result = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)

class Budget(Base):
    """
    Represents the Budget entity and its core operations.
    """
    __tablename__ = "budgets"
    
    principal_id = Column(String, primary_key=True)
    max_budget = Column(Float, nullable=False)
    consumed_budget = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="USD")
