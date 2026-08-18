"""
@file tests/integration/test_workflow_engine.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.domain.models.workflow import Workflow, WorkflowVersion, WorkflowState
from app.workflows.engine import WorkflowEngine
from app.core.security import Principal

# Use SQLite in-memory for fast integration testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_workflow(db_session):
    wf = Workflow(name="Test Workflow", workspace_id="ws-123")
    db_session.add(wf)
    db_session.commit()
    
    definition = {
        "steps": [
            {"id": "step_1", "action": "tool_call", "requires_approval": False},
            {"id": "step_2", "action": "agent_task", "requires_approval": True}
        ]
    }
    
    version = WorkflowVersion(workflow_id=wf.id, version_number=1, definition=definition)
    db_session.add(version)
    db_session.commit()
    return version

def test_start_workflow(db_session, sample_workflow):
    """M10: Test that a workflow can be started and checkpoints correctly."""
    engine = WorkflowEngine(db_session)
    run = engine.start_workflow(version_id=sample_workflow.id, session_id="session-456", input_data={"url": "http://test.com"})
    
    assert run is not None
    assert run.status == WorkflowState.QUEUED
    assert run.state_checkpoint["variables"]["url"] == "http://test.com"
    assert len(run.state_checkpoint["completed_steps"]) == 0

def test_workflow_human_approval_pause(db_session, sample_workflow):
    """M10: Test that workflow pauses correctly on WAITING_APPROVAL."""
    engine = WorkflowEngine(db_session)
    run = engine.start_workflow(version_id=sample_workflow.id, session_id="session-456", input_data={})
    
    # Simulate first step execution
    engine.execute_step(run.id)
    db_session.refresh(run)
    assert "step_1" in run.state_checkpoint["completed_steps"]
    
    # Simulate second step (requires approval)
    engine.execute_step(run.id)
    db_session.refresh(run)
    assert run.status == WorkflowState.WAITING_APPROVAL
    assert run.current_step == "step_2"

def test_workflow_resume_from_approval(db_session, sample_workflow):
    """M10: Test that workflow resumes from checkpoint when human approves."""
    wf_engine = WorkflowEngine(db_session)
    run = wf_engine.start_workflow(version_id=sample_workflow.id, session_id="session-456", input_data={})
    
    # Force state to WAITING_APPROVAL for step 2
    run.status = WorkflowState.WAITING_APPROVAL
    run.current_step = "step_2"
    db_session.commit()
    
    principal = Principal(id="admin-99", roles=["admin"], workspace_id="ws-123")
    
    # Resume
    wf_engine.resume_from_approval(run.id, approved=True, approved_by=principal)
    db_session.refresh(run)
    
    assert run.status == WorkflowState.RUNNING
    assert "step_2" in run.state_checkpoint["completed_steps"]
    assert "Approved by admin-99" in run.state_checkpoint["variables"]["step_2_approval"]
