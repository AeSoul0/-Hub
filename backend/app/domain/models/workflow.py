"""
@file backend/app/domain/models/workflow.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Enum, Boolean, Integer
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
import uuid

from app.core.db import Base

class TriggerType(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"
    TASK_COMPLETION = "task_completion"
    FILE_ARRIVAL = "file_arrival"
    AGENT_DECISION = "agent_decision"

class WorkflowState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    workspace_id = Column(String, nullable=False) # Tenant isolation
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan")

class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    definition = Column(JSON, nullable=False) # The DAG structure: steps and transitions
    created_at = Column(DateTime, default=datetime.utcnow)
    
    workflow = relationship("Workflow", back_populates="versions")
    runs = relationship("WorkflowRun", back_populates="version")

class WorkflowTrigger(Base):
    __tablename__ = "workflow_triggers"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_version_id = Column(String, ForeignKey("workflow_versions.id"), nullable=False)
    type = Column(Enum(TriggerType), nullable=False)
    configuration = Column(JSON, nullable=True) # e.g. cron expression, webhook secret
    is_active = Column(Boolean, default=True)

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_version_id = Column(String, ForeignKey("workflow_versions.id"), nullable=False)
    session_id = Column(String, nullable=False) # Tie execution to a user session/principal
    status = Column(Enum(WorkflowState), default=WorkflowState.QUEUED)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    current_step = Column(String, nullable=True)
    state_checkpoint = Column(JSON, nullable=True) # Enables Resumability
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    
    version = relationship("WorkflowVersion", back_populates="runs")
