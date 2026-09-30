"""
@file backend/app/agent_engine/models.py
@description Core domain models and schemas for the native A.U.R.O.R.A. Agent Engine.

This module defines the strongly typed contracts used by the orchestration runtime,
tool execution layer, policy engine, approval system, memory subsystem, and evaluation
pipeline. The models are intentionally independent from persistence implementations so
the runtime can operate deterministically while durable state is serialized separately.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRunStatus(str, Enum):
    """Lifecycle states supported by the native Agent Runtime."""

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
    Durable execution model for a single native Agent Runtime run.

    The complete runtime checkpoint is represented by this model and may be
    serialized into the persistence layer without depending on ORM internals.
    """

    run_id: str
    parent_run_id: Optional[str] = None

    session_id: str
    workspace_id: str

    principal_id: Optional[str] = None
    role: str = "agent"

    status: AgentRunStatus = AgentRunStatus.QUEUED

    metadata: Dict[str, Any] = Field(default_factory=dict)
    current_state: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Any] = Field(default_factory=list)

    task_attempts: int = 0
    errors: List[str] = Field(default_factory=list)

    usage: Dict[str, Any] = Field(default_factory=dict)

    result: Any = None
    error: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RunContext(BaseModel):
    """
    Execution context scoped to a single run and workspace.
    """

    run_id: str
    workspace_id: str
    history: List[Any] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentIntent(BaseModel):
    """Normalized intent representation produced by the orchestration layer."""

    intent: str
    confidence: float


class TaskExecution(BaseModel):
    """Execution metadata for orchestrated and delegated tasks."""

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
    Declarative specification for an executable tool.

    ToolSpec is the canonical contract consumed by PolicyEngine and ToolGateway.
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
    """Tool request emitted by a Worker and evaluated by the ToolGateway."""

    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    run_id: str


class PolicyDecisionEnum(str, Enum):
    """Possible authorization outcomes produced by PolicyEngine."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyDecision(BaseModel):
    """Structured result returned by PolicyEngine."""

    decision: PolicyDecisionEnum
    reason: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Runtime representation of an approval request."""

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
    """Execution metadata for a single tool call."""

    tool_call_id: str
    status: str
    started_at: datetime = Field(default_factory=datetime.utcnow)


class ToolResult(BaseModel):
    """Canonical tool result returned to the runtime."""

    tool_call_id: str
    result: Any
    error: Optional[str] = None


class Observation(BaseModel):
    """Observation produced by a tool execution and fed back to the Worker."""

    tool_call_id: str
    content: Any


class CheckerDecisionEnum(str, Enum):
    """
    Decision states emitted by the independent Checker.

    ACCEPT:
        The generated result satisfies the required criteria.

    RETRY:
        The result is recoverably incorrect and should be regenerated.

    FAIL:
        The result or execution path is irrecoverably invalid.
    """

    ACCEPT = "ACCEPT"
    RETRY = "RETRY"
    FAIL = "FAIL"


class CheckerIssue(BaseModel):
    """Structured issue reported by the Checker."""

    code: str
    severity: str


class CheckerDecision(BaseModel):
    """Structured evaluation result returned by the Checker."""

    status: CheckerDecisionEnum
    issues: List[CheckerIssue] = Field(default_factory=list)
    retry_instruction: Optional[str] = None


class RetryInstruction(BaseModel):
    """Explicit instruction used to guide a retry iteration."""

    instruction: str
    attempt: int


class MemoryContext(BaseModel):
    """Scoped memory context attached to an execution."""

    context_id: str
    data: Dict[str, Any]


class RunEvent(BaseModel):
    """Serializable runtime event used by the observability subsystem."""

    event_type: str
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict)


class RunUsage(BaseModel):
    """Aggregate resource usage information for a run."""

    run_id: str
    tokens: int
    cost: float
    latency: float