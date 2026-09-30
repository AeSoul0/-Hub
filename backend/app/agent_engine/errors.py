"""
@file backend/app/agent_engine/errors.py
@description Implements errors.py. Core components: AgentEngineError, ToolExecutionError, PolicyViolationError, MaxTurnsReachedError, TaskTimeoutError, ApprovalRequiredError, StateRecoveryError.

This module manages the internal business logic for AgentEngineError, ToolExecutionError, PolicyViolationError, MaxTurnsReachedError, TaskTimeoutError, ApprovalRequiredError, StateRecoveryError.
It provides specialized functionality to handle: utility operations.
"""
class AgentEngineError(Exception):
    """
    Represents the AgentEngineError entity and its core operations.
    """
    """Base exception for all Agent Engine errors."""
    pass

class ToolExecutionError(AgentEngineError):
    """
    Represents the ToolExecutionError entity and its core operations.
    """
    """Raised when a tool execution fails."""
    pass

class PolicyViolationError(AgentEngineError):
    """
    Represents the PolicyViolationError entity and its core operations.
    """
    """Raised when an action violates the configured policy."""
    pass

class MaxTurnsReachedError(AgentEngineError):
    """
    Represents the MaxTurnsReachedError entity and its core operations.
    """
    """Raised when the maximum number of turns is reached in an orchestration loop."""
    pass

class TaskTimeoutError(AgentEngineError):
    """
    Represents the TaskTimeoutError entity and its core operations.
    """
    """Raised when a task exceeds its execution deadline."""
    pass

class ApprovalRequiredError(AgentEngineError):
    """
    Represents the ApprovalRequiredError entity and its core operations.
    """
    """Raised when an execution requires approval but hasn't received it."""
    pass

class StateRecoveryError(AgentEngineError):
    """
    Represents the StateRecoveryError entity and its core operations.
    """
    """Raised when the engine fails to recover a durable run state."""
    pass
