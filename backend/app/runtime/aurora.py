"""
@file backend/app/runtime/aurora.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import operator
import os
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
# ChatGroq import removed in favor of ModelRouter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from psycopg_pool import AsyncConnectionPool

from app.core.security import PolicyEngine, Principal


# Define the State for our Agentic System
class AuroraState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str
    current_intent: str
    principal: Principal

import app.skills.memory_skill as memory_skill_module
from app.memory.manager import AuroraMemoryManager
from app.skills import skill_registry

# Load all skills dynamically
skill_registry.load_from_package("app.skills")

# Get aggregated tools
tools = skill_registry.get_all_tools()
safe_tools = []
sensitive_tools = []

for t in tools:
    meta = skill_registry._tool_metadata.get(t.name)
    if meta and meta.requires_approval:
        sensitive_tools.append(t)
    else:
        safe_tools.append(t)

safe_tool_node = ToolNode(safe_tools) if safe_tools else None
sensitive_tool_node = ToolNode(sensitive_tools) if sensitive_tools else None

# Node: Agent
async def agent_node(state: AuroraState):
    messages = state["messages"]
    session_id = state.get("session_id", "default-session")
    
    # Set the contextvar for tools that need it (like MemorySkill)
    memory_skill_module.current_session_id.set(session_id)
    
    from app.core.models import ModelRouter, ModelProvider
    from app.core.config import settings
    llm = ModelRouter.get_model(
        provider=ModelProvider.GROQ,
        model_name=settings.DEFAULT_LLM_MODEL,
        temperature=settings.DEFAULT_TEMPERATURE
    )
    
    # Only bind tools if there are tools available
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm
    
    # Retrieve memories
    memory_manager = AuroraMemoryManager(session_id)
    memories_text = memory_manager.fetch_all_context()
    
    # Phase 5: Dynamic System Prompt based on Identity Role
    principal = state.get("principal")
    role_str = principal.role.value if principal else "USER"
    
    base_system_prompt = (
        f"You are A.U.R.O.R.A. (Autonomous Uplink & Real-time Operations Robotic Assistant). "
        f"You are operating with authority level: {role_str}. "
        "Be concise, act as the core orchestrator. Always respond in Italian unless requested otherwise."
    )
    
    skill_extensions = skill_registry.get_system_prompt_extensions()
    
    final_prompt = base_system_prompt
    if memories_text:
        final_prompt += "\n\n[CONTEXT MEMORY]\n" + memories_text
        
    if skill_extensions:
        final_prompt += "\n\n[AVAILABLE CAPABILITIES]\n" + skill_extensions
        
    system_msg = {"role": "system", "content": final_prompt}
    
    # Prepend system message
    full_messages = [system_msg] + list(messages)
    
    response = await llm_with_tools.ainvoke(full_messages)
    return {"messages": [response]}

from app.runtime.tool_gateway import ToolGateway, ToolInvocation, ToolSpec, RiskLevel

# Node: Execute Tools via Gateway
async def execute_tools_node(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    principal = state.get("principal")
    session_id = state.get("session_id", "default-session")
    
    if not principal:
        return {"messages": []} # Fallback, should never happen
        
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        results = []
        for tc in last_message.tool_calls:
            tool_name = tc["name"]
            arguments = tc["args"]
            
            tool_instance = next((t for t in tools if t.name == tool_name), None)
            if not tool_instance:
                from langchain_core.messages import ToolMessage
                results.append(ToolMessage(tool_call_id=tc["id"], name=tool_name, content="Error: Tool not found"))
                continue
                
            meta = skill_registry._tool_metadata.get(tool_name)
            spec = ToolSpec(
                name=tool_name,
                description=tool_instance.description,
                risk_level=RiskLevel.HIGH if (meta and meta.requires_approval) else RiskLevel.LOW,
                approval_required=meta.requires_approval if meta else False
            )
            
            invocation = ToolInvocation(
                tool_name=tool_name,
                arguments=arguments,
                principal=principal,
                session_id=session_id,
                spec=spec
            )
            
            async def executor(**kwargs):
                # Handle execution of LangChain BaseTool
                if hasattr(tool_instance, "ainvoke"):
                    return await tool_instance.ainvoke(kwargs)
                else:
                    return tool_instance.invoke(kwargs)
                    
            res = await ToolGateway.execute(invocation, executor)
            
            from langchain_core.messages import ToolMessage
            if res.success:
                results.append(ToolMessage(tool_call_id=tc["id"], name=tool_name, content=res.output))
            else:
                results.append(ToolMessage(tool_call_id=tc["id"], name=tool_name, content=f"Policy/Execution Error: {res.error}"))
                
        return {"messages": results}
    
    return {"messages": []}

# Conditional edge from agent to tools
def should_execute_tools(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "execute_tools"
    return END

# Build the Graph
workflow = StateGraph(AuroraState)
workflow.add_node("agent", agent_node)
workflow.add_node("execute_tools", execute_tools_node)

workflow.add_conditional_edges("agent", should_execute_tools, {"execute_tools": "execute_tools", END: END})
workflow.add_edge("execute_tools", "agent")

workflow.set_entry_point("agent")

_aurora_app = None
_pool = None

async def get_aurora_app():
    """Lazily initializes the LangGraph application with PostgreSQL Checkpointer."""
    global _aurora_app, _pool
    if _aurora_app is not None:
        return _aurora_app
        
    from app.core.config import settings
    
    _pool = AsyncConnectionPool(
        conninfo=settings.POSTGRES_URL,
        max_size=20,
        kwargs={"autocommit": True}
    )
    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()
    
    _aurora_app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["sensitive_tools"] if sensitive_tool_node else None
    )
    return _aurora_app
