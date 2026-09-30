"""
@file backend/app/agent_engine/adapters/langchain_adapter.py
@description Implements langchain_adapter.py. Core components: LangchainModelAdapter.

This module manages the internal business logic for LangchainModelAdapter.
It provides specialized functionality to handle: generate.
"""
from typing import Dict, Any, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from app.agent_engine.adapters.base import ModelProvider
from app.agent_engine.models import ToolProposal

class LangchainModelAdapter(ModelProvider):
    """
    Represents the LangchainModelAdapter entity and its core operations.
    """
    """
    Implements the ModelProvider interface by delegating execution to a 
    LangChain BaseChatModel instance. Manages message history formatting 
    and translates LangChain tool calls into native ToolProposal objects.
    """
    
    def __init__(self, model: BaseChatModel, tools: List[Any] = None, **kwargs):
        """
        Executes __init__ logic.
        """
        """
        Initializes the adapter with a specific LangChain model and an optional toolset.
        Binds the tools to the model if provided.
        """
        super().__init__(model_name=model.model_name if hasattr(model, 'model_name') else "unknown", **kwargs)
        self.model = model
        self.tools = tools or []
        
        # Bind tools to the model to enable function calling capabilities
        if self.tools:
            self.model_with_tools = self.model.bind_tools(self.tools)
        else:
            self.model_with_tools = self.model

    async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes generate logic.
        """
        """
        Processes the internal task context and generates a response using the LangChain model.
        It translates internal observations and feedback into LangChain message primitives.
        """
        # Extract task details and constraints from the execution context
        task = context.get("task", {}).get("description", str(context.get("task", "")))
        observations = context.get("observations", [])
        feedback = context.get("feedback")
        system_prompt = context.get("system_prompt", "You are an intelligent agent.")
        
        # Construct the conversation history for the LLM
        messages = [SystemMessage(content=system_prompt)]
        messages.append(HumanMessage(content=task))
        
        # Append checker feedback if the previous execution iteration was rejected
        if feedback:
            messages.append(HumanMessage(content=f"Checker Feedback: {feedback}"))
            
        # Append tool execution results (observations) from the sandbox
        for obs in observations:
            messages.append(ToolMessage(tool_call_id=obs.tool_call_id, content=str(obs.content), name="tool"))
            
        # Invoke the LangChain model asynchronously
        response = await self.model_with_tools.ainvoke(messages)
        
        tool_proposals = []
        # Parse LangChain tool calls and map them to native ToolProposal structures
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_proposals.append(ToolProposal(
                    tool_call_id=tc["id"],
                    tool_name=tc["name"],
                    arguments=tc["args"],
                    run_id="run_placeholder" # Expected to be injected by the runtime environment
                ))
                
        return {
            "output": response.content,
            "tool_proposals": tool_proposals
        }
