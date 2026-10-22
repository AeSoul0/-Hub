"""
@file backend/app/domain/models/audit.py
@description Implements audit.py. Core components: AuditLog, ApprovalRecord.

This module manages the internal business logic for AuditLog, ApprovalRecord.
It provides specialized functionality to handle: utility operations.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text

from app.domain.models.identity import Base

class AuditLog(Base):
    """
    Represents the AuditLog entity and its core operations.
    """
    """
    Immutable audit record for tool executions and system actions.
    Enforces M2 observability requirement.
    """
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    session_id = Column(String, nullable=False, index=True)
    run_id = Column(String, nullable=True)
    tool_call_id = Column(String, nullable=True)
    principal_id = Column(String, nullable=False)
    workspace_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    risk = Column(String, nullable=False, default="low")
    arguments_hash = Column(String, nullable=True)
    decision = Column(String, nullable=True)
    success = Column(Boolean, nullable=False)
    execution_result = Column(Text, nullable=True)
    duration = Column(String, nullable=True)
    error = Column(Text, nullable=True)

class AuditChainLink(Base):
    """
    Tamper-evident hash chain over AuditLog rows.

    Each link stores the SHA-256 of its audit row chained to the previous
    link, so editing or deleting a row breaks every later hash. The chain
    lives in its own table so existing databases pick it up through
    create_all without a migration.
    """
    __tablename__ = "audit_chain"

    seq = Column(Integer, primary_key=True, autoincrement=False)
    audit_id = Column(String, nullable=False, unique=True, index=True)
    prev_hash = Column(String(64), nullable=False)
    record_hash = Column(String(64), nullable=False)

class ApprovalRecord(Base):
    """
    Represents the ApprovalRecord entity and its core operations.
    """
    __tablename__ = "approvals"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, nullable=True)
    session_id = Column(String, nullable=False)
    workspace_id = Column(String, nullable=False)
    tool = Column(String, nullable=False)
    arguments_hash = Column(String, nullable=False)
    risk = Column(String, nullable=False, default="low")
    requested_by = Column(String, nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    decision = Column(String, nullable=True)
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime, nullable=True)
