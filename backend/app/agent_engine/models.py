"""
@file backend/app/agent_engine/models.py
@description Core Domain Models and Schemas for the A.U.R.O.R.A. Agent Engine.

This foundational module defines the comprehensive suite of Pydantic models and Enumerations 
that dictate data structures and schemas across the orchestration layer. It encapsulates models 
for state transitions (`AgentRunStatus`), executable tasks (`TaskExecution`), interactive tool 
blueprints (`ToolSpec`, `ToolProposal`, `ToolResult`), and rigorous policy or evaluation constructs 
such as `PolicyDecision` and `CheckerDecision`. These strictly typed structures enforce consistency, 
facilitate deterministic API contracts, and provide seamless serialization bounds for distributed 
asynchronous multi-agent operations.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class AgentRunStatus(str, Enum):
    """
    Represents the AgentRunStatus entity and its core operations.
    """
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_TOOL = "waiting_tool"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class AgentRun(BaseModel):
    """
    Represents the AgentRun entity and its core operations.
    """
    run_id: str
    parent_run_id: Optional[str] = None
    session_id: str
    workspace_id: str
    status: AgentRunStatus = AgentRunStatus.QUEUED
    metadata: Dict[str, Any] = Field(default_factory=dict)
    current_state: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Any] = Field(default_factory=list)
    task_attempts: int = 0
    errors: List[str] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RunContext(BaseModel):
    """
    Represents the RunContext entity and its core operations.
    """
    run_id: str
    workspace_id: str
    history: List[Any] = []
    metadata: Dict[str, Any] = {}

class AgentIntent(BaseModel):
    """
    Represents the AgentIntent entity and its core operations.
    """
    intent: str
    confidence: float

class TaskExecution(BaseModel):
    """
    Represents the TaskExecution entity and its core operations.
    """
    task_id: str
    parent_run_id: Optional[str] = None
    orchestrator_run_id: str
    subagent_run_id: Optional[str] = None
    checker_run_id: Optional[str] = None
    attempt: int = 1
    max_attempts: int = 3
    status: str
    feedback: Optional[str] = None

class ToolSpec(BaseModel):
    """
    Represents the ToolSpec entity and its core operations.
    """
    name: str
    version: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    risk_level: str
    permissions: List[str]
    network_access: bool
    filesystem_access: bool
    max_runtime: int
    max_output: int
    max_cost: float
    idempotent: bool
    requires_approval: bool
    sandbox_profile: str
    audit_policy: str

class ToolProposal(BaseModel):
    """
    Represents the ToolProposal entity and its core operations.
    """
    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    run_id: str

class PolicyDecisionEnum(str, Enum):
    """
    Represents the PolicyDecisionEnum entity and its core operations.
    """
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

class PolicyDecision(BaseModel):
    """
    Represents the PolicyDecision entity and its core operations.
    """
    decision: PolicyDecisionEnum
    reason: Optional[str] = None

class ApprovalRequest(BaseModel):
    """
    Represents the ApprovalRequest entity and its core operations.
    """
    id: str
    run_id: str
    tool_call_id: str
    tool: str
    arguments: Dict[str, Any]
    risk: str
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    requested_by: str
    decided_by: Optional[str] = None
    decision: Optional[str] = None

class ToolExecution(BaseModel):
    """
    Represents the ToolExecution entity and its core operations.
    """
    tool_call_id: str
    status: str
    started_at: datetime = Field(default_factory=datetime.utcnow)

class ToolResult(BaseModel):
    """
    Represents the ToolResult entity and its core operations.
    """
    tool_call_id: str
    result: Any
    error: Optional[str] = None

class Observation(BaseModel):
    """
    Represents the Observation entity and its core operations.
    """
    tool_call_id: str
    content: Any

class CheckerDecisionEnum(str, Enum):
    """
    Enumerates the possible categorical outcomes yielded by the independent Checker.
    
    Attributes:
        ACCEPT: The payload fully complies with the structural constraints and user instructions.
        RETRY: The payload exhibits recoverable flaws; iterative correction is advised.
        FAIL: The payload is irrecoverably flawed or violates critical policies.
    """
    ACCEPT = "ACCEPT"
    RETRY = "RETRY"
    FAIL = "FAIL"

class CheckerIssue(BaseModel):
    """
    Represents a granular issue identified during the Checker's evaluation phase.
    
    Attributes:
        code (str): Machine-readable identifier for the anomaly class.
        severity (str): Impact ranking, such as 'HIGH', 'MEDIUM', or 'LOW'.
    """
    code: str
    severity: str

class CheckerDecision(BaseModel):
    """
    Aggregates the comprehensive output state of the independent evaluation phase.
    
    Provides the core routing signal (`status`) alongside deterministic arrays of 
    identified errors (`issues`) and precise linguistic instructions (`retry_instruction`) 
    intended to steer the worker through subsequent corrective generations.
    """
    status: CheckerDecisionEnum
    issues: List[CheckerIssue] = []
    retry_instruction: Optional[str] = None

class RetryInstruction(BaseModel):
    """
    Represents the RetryInstruction entity and its core operations.
    """
    instruction: str
    attempt: int

class MemoryContext(BaseModel):
    """
    Represents the MemoryContext entity and its core operations.
    """
    context_id: str
    data: Dict[str, Any]

class RunEvent(BaseModel):
    """
    Represents the RunEvent entity and its core operations.
    """
    event_type: str
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = {}

class RunUsage(BaseModel):
    """
    Represents the RunUsage entity and its core operations.
    """
    run_id: str
    tokens: int
    cost: float
    latency: float
