"""
@file backend/app/agent_engine/context.py
@description Implements context.py. Core components: ContextManager.

This module manages the internal business logic for ContextManager.
It provides specialized functionality to handle: add_event_to_history, get_history, update_metadata, add_memory.
"""
from typing import Dict, Any, List
from app.agent_engine.models import RunContext, MemoryContext

class ContextManager:
    """
    Represents the ContextManager entity and its core operations.
    """
    """Manages the execution context for an agent run."""
    
    def __init__(self, run_id: str, workspace_id: str):
        """
        Executes __init__ logic.
        """
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
        """
        Executes add_event_to_history logic.
        """
        # Append a new event to the main context history
        self.context.history.append(event)
        
    def get_history(self) -> List[Any]:
        """
        Executes get_history logic.
        """
        # Retrieve the full event history of the run
        return self.context.history

    def update_metadata(self, key: str, value: Any) -> None:
        """
        Executes update_metadata logic.
        """
        # Add or update a key-value pair in the context metadata
        self.context.metadata[key] = value

    def add_memory(self, memory_id: str, data: Dict[str, Any]) -> None:
        """
        Executes add_memory logic.
        """
        # Store a new memory context with the given ID and data
        self.memory_contexts[memory_id] = MemoryContext(context_id=memory_id, data=data)
