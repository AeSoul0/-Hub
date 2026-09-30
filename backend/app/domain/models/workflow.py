"""
@file backend/app/domain/models/workflow.py
@description Implements workflow.py. Core components: TriggerType, WorkflowState, Workflow, WorkflowVersion, WorkflowTrigger, WorkflowRun.

This module manages the internal business logic for TriggerType, WorkflowState, Workflow, WorkflowVersion, WorkflowTrigger, WorkflowRun.
It provides specialized functionality to handle: utility operations.
"""
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Enum, Boolean, Integer
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
import uuid

from app.core.db import Base

class TriggerType(str, enum.Enum):
    """
    Represents the TriggerType entity and its core operations.
    """
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"
    TASK_COMPLETION = "task_completion"
    FILE_ARRIVAL = "file_arrival"
    AGENT_DECISION = "agent_decision"

class WorkflowState(str, enum.Enum):
    """
    Represents the WorkflowState entity and its core operations.
    """
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Workflow(Base):
    """
    Represents the Workflow entity and its core operations.
    """
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    workspace_id = Column(String, nullable=False) # Tenant isolation
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan")

class WorkflowVersion(Base):
    """
    Represents the WorkflowVersion entity and its core operations.
    """
    __tablename__ = "workflow_versions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    definition = Column(JSON, nullable=False) # The DAG structure: steps and transitions
    created_at = Column(DateTime, default=datetime.utcnow)
    
    workflow = relationship("Workflow", back_populates="versions")
    runs = relationship("WorkflowRun", back_populates="version")

class WorkflowTrigger(Base):
    """
    Represents the WorkflowTrigger entity and its core operations.
    """
    __tablename__ = "workflow_triggers"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_version_id = Column(String, ForeignKey("workflow_versions.id"), nullable=False)
    type = Column(Enum(TriggerType), nullable=False)
    configuration = Column(JSON, nullable=True) # e.g. cron expression, webhook secret
    is_active = Column(Boolean, default=True)

class WorkflowRun(Base):
    """
    Represents the WorkflowRun entity and its core operations.
    """
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
