"""
@file backend/app/agents/subagents/base.py
@description Subagent factory (Phase 12 LangGraph Removal).

Completely removes LangGraph dependencies. Subagents are now native
Worker instances that wrap the ModelProvider interface. The tool execution
loop is handled exclusively by the AgentRuntime.
"""

from typing import List, Callable, Dict, Any, Optional
from app.core.security import Principal, SubagentCapabilitySet
from app.agent_engine.adapters.base import ModelProvider

class NativeWorker:
    """
    A worker that complies with the native AEHub AgentRuntime interface,
    wrapping an injected ModelProvider.
    """
    def __init__(self, role_name: str, system_prompt: str, tools: List[Callable], adapter: ModelProvider, capabilities: SubagentCapabilitySet):
        self.role_name = role_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.adapter = adapter
        self.capabilities = capabilities
        
    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # Inject system prompt into context for the adapter
        context["system_prompt"] = self.system_prompt
        context["role"] = self.role_name
        # The adapter evaluates context (task, feedback, observations) and generates next action
        return await self.adapter.generate(context)

class SubagentFactory:
    """
    Creates specialized sub-workers.
    """
    
    @staticmethod
    def create_subagent(role_name: str, system_prompt: str, tools: List[Callable], adapter: ModelProvider, capabilities: SubagentCapabilitySet) -> NativeWorker:
        return NativeWorker(role_name, system_prompt, tools, adapter, capabilities)

