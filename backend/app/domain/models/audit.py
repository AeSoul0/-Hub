"""
@file backend/app/domain/models/audit.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text

from app.domain.models.identity import Base

class AuditLog(Base):
    """
    Immutable audit record for tool executions and system actions.
    Enforces M2 observability requirement.
    """
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    session_id = Column(String, nullable=False, index=True)
    principal_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)
