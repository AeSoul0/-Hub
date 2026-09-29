"""
@file backend/app/agent_engine/models.py
@description Core Data Models for the Agent Engine.

Defines the exact structures for Agent Runs, Orchestration States, Policy Decisions, and Memory contexts.
Includes strictly typed Pydantic models to enforce Phase 5 Durable Agent Runs and state synchronization.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class AgentRunStatus(str, Enum):
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
    run_id: str
    workspace_id: str
    history: List[Any] = []
    metadata: Dict[str, Any] = {}

class AgentIntent(BaseModel):
    intent: str
    confidence: float

class TaskExecution(BaseModel):
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
    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    run_id: str

class PolicyDecisionEnum(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

class PolicyDecision(BaseModel):
    decision: PolicyDecisionEnum
    reason: Optional[str] = None

class ApprovalRequest(BaseModel):
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
    tool_call_id: str
    status: str
    started_at: datetime = Field(default_factory=datetime.utcnow)

class ToolResult(BaseModel):
    tool_call_id: str
    result: Any
    error: Optional[str] = None

class Observation(BaseModel):
    tool_call_id: str
    content: Any

class CheckerDecisionEnum(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"

class CheckerDecision(BaseModel):
    status: CheckerDecisionEnum
    issues: List[str] = []
    retry_instruction: Optional[str] = None

class RetryInstruction(BaseModel):
    instruction: str
    attempt: int

class MemoryContext(BaseModel):
    context_id: str
    data: Dict[str, Any]

class RunEvent(BaseModel):
    event_type: str
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = {}

class RunUsage(BaseModel):
    run_id: str
    tokens: int
    cost: float
    latency: float
