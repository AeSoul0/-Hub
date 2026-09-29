"""
@file backend/app/agent_engineerrors.py
@description Core module for A.U.R.O.R.A. System Engine.

Implements architectural specifications according to the project roadmap.
Ensures durable execution, secure boundaries, and strict multi-agent orchestration.
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
    pass

class StateRecoveryError(AgentEngineError):
    """Raised when the engine fails to recover a durable run state."""
    pass
