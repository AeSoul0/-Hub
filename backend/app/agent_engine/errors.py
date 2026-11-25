"""
@file backend/app/agent_engine/errors.py
@description The engine's exceptions: tool failures, policy violations, limits, approvals and state recovery.
"""
class AgentEngineError(Exception):
    """Base exception for all Agent Engine errors."""
    pass

class ToolExecutionError(AgentEngineError):
    """Raised when a tool execution fails."""
    pass

class PolicyViolationError(AgentEngineError):
    """Raised when an action violates the configured policy."""
    pass

class MaxTurnsReachedError(AgentEngineError):
    """Raised when the maximum number of turns is reached in an orchestration loop."""
    pass

class TaskTimeoutError(AgentEngineError):
    """Raised when a task exceeds its execution deadline."""
    pass

class ApprovalRequiredError(AgentEngineError):
    """Raised when an execution requires approval but hasn't received it."""

    def __init__(self, message: str = "", approval_id: str | None = None) -> None:
        super().__init__(message)
        self.approval_id = approval_id

class StateRecoveryError(AgentEngineError):
    """Raised when the engine fails to recover a durable run state."""
    pass


class RunInterrupted(AgentEngineError):
    """
    Base class for conditions that stop a run between or during steps.
    """

    status = "failed"


class RunCancelledError(RunInterrupted):
    """Raised when a run is cancelled by its owner or by the global stop."""

    status = "cancelled"


class BudgetExceededError(RunInterrupted):
    """Raised when a run or the monthly spend cap is exhausted."""

    status = "failed"


class RunLimitExceededError(RunInterrupted):
    """Raised when a run hits a non-spend limit (failed tool calls, modified files)."""

    status = "failed"
