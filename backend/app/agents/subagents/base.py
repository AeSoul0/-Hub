"""
@file backend/app/agents/subagents/base.py
@description Native subagent worker and factory implementation.

Provides the adapter-backed Worker implementation used by AgentRuntime.
The worker is deliberately framework-agnostic: no LangGraph graph is created,
compiled, or invoked at this boundary.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.agent_engine.adapters.base import ModelProvider
from app.core.security import SubagentCapabilitySet


# ==============================================================================
# NATIVE WORKER
# ==============================================================================

class NativeWorker:
    """
    Adapter-backed worker compatible with AgentRuntime.
    """

    def __init__(
        self,
        role_name: str,
        system_prompt: str,
        tools: List[Callable[..., Any]],
        adapter: ModelProvider,
        capabilities: SubagentCapabilitySet,
    ) -> None:
        self.role_name = role_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.adapter = adapter
        self.capabilities = capabilities

    async def generate(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generates the next worker action using the configured ModelProvider.

        The original context is copied so the worker does not mutate durable
        runtime state outside the explicit result returned to AgentRuntime.
        """
        adapter_context = dict(context)
        adapter_context["system_prompt"] = self.system_prompt
        adapter_context["role"] = self.role_name
        adapter_context["capabilities"] = self.capabilities.model_dump()

        return await self.adapter.generate(adapter_context)


# ==============================================================================
# SUBAGENT FACTORY
# ==============================================================================

class SubagentFactory:
    """
    Factory responsible for constructing native subagent workers.
    """

    @staticmethod
    def create_subagent(
        role_name: str,
        system_prompt: str,
        tools: List[Callable[..., Any]],
        adapter: ModelProvider,
        capabilities: SubagentCapabilitySet,
    ) -> NativeWorker:
        """
        Creates a NativeWorker with explicit delegated capabilities.
        """
        if not role_name:
            raise ValueError("role_name is required.")

        if not isinstance(capabilities, SubagentCapabilitySet):
            raise TypeError(
                "capabilities must be a SubagentCapabilitySet instance."
            )

        return NativeWorker(
            role_name=role_name,
            system_prompt=system_prompt,
            tools=tools,
            adapter=adapter,
            capabilities=capabilities,
        )