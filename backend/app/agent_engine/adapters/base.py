"""
@file backend/app/agent_engine/adapters/base.py
@description The interface every model adapter implements: one generate() per turn.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any

class ModelProvider(ABC):
    """
    Abstract base class for all language model adapters.
    The ÆHub Runtime interacts exclusively with this interface.
    """
    
    def __init__(self, model_name: str, **kwargs):
        """Keep the model name and the provider options."""
        self.model_name = model_name
        self.config = kwargs

    @abstractmethod
    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a response from the model.
        Must return a standardized dictionary containing at minimum:
        - "output": The text response.
        - "tool_proposals": A list of ToolProposal objects (if any).
        """
        pass
