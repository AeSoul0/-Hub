"""
@file backend/app/agent_engine\context.py
@description Core module for A.U.R.O.R.A. System Engine.

Implements architectural specifications according to the project roadmap.
Ensures durable execution, secure boundaries, and strict multi-agent orchestration.
"""

from typing import Dict, Any, List
from app.agent_engine.models import RunContext, MemoryContext

class ContextManager:
    """Manages the execution context for an agent run."""
    
    def __init__(self, run_id: str, workspace_id: str):
        # Initialize the main run context with an empty history and metadata
        self.context = RunContext(
            run_id=run_id,
            workspace_id=workspace_id,
            history=[],
            metadata={}
        )
        # Initialize a dictionary to store separate memory contexts
        self.memory_contexts: Dict[str, MemoryContext] = {}

    def add_event_to_history(self, event: Any) -> None:
        # Append a new event to the main context history
        self.context.history.append(event)
        
    def get_history(self) -> List[Any]:
        # Retrieve the full event history of the run
        return self.context.history

    def update_metadata(self, key: str, value: Any) -> None:
        # Add or update a key-value pair in the context metadata
        self.context.metadata[key] = value

    def add_memory(self, memory_id: str, data: Dict[str, Any]) -> None:
        # Store a new memory context with the given ID and data
        self.memory_contexts[memory_id] = MemoryContext(context_id=memory_id, data=data)
