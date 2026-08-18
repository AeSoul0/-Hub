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
from langchain_groq import ChatGroq
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
    
    llm = ChatGroq(
        model="llama-3.2-90b-vision-preview",
        temperature=0.75,
        api_key=os.getenv("GROQ_API_KEY")
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

# Node: Policy Gateway
async def policy_gateway_node(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    principal = state.get("principal")
    
    if not principal:
        return {"messages": []} # Fallback, should never happen
        
    # Check if any requested tool violates policy
    denied = []
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tc in last_message.tool_calls:
            is_sensitive = any(t.name == tc["name"] for t in sensitive_tools)
            decision = PolicyEngine.authorize_tool(principal, is_sensitive)
            if not decision.allowed:
                denied.append((tc, decision.reason))
                
    if denied:
        # We must return a ToolMessage for each denied call to satisfy the LLM
        from langchain_core.messages import ToolMessage
        error_msgs = []
        for tc, reason in denied:
            error_msgs.append(ToolMessage(
                tool_call_id=tc["id"], 
                name=tc["name"], 
                content=f"Security Policy Violation: {reason}"
            ))
        return {"messages": error_msgs}
    
    return {"messages": []}

# Conditional edge from agent to gateway
def should_continue_to_gateway(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "policy_gateway"
    return END
    
# Conditional edge from gateway to tools or back to agent
def route_from_gateway(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the gateway added ToolMessages (denials), route back to agent
    from langchain_core.messages import ToolMessage
    if isinstance(last_message, ToolMessage):
        return "agent"
        
    # Otherwise, find the original AIMessage with tool calls
    ai_msg = messages[-1]
    for m in reversed(messages):
        if hasattr(m, "tool_calls") and m.tool_calls:
            ai_msg = m
            break
            
    for tc in ai_msg.tool_calls:
        if any(t.name == tc["name"] for t in sensitive_tools):
            return "sensitive_tools"
    return "safe_tools"

# Build the Graph
workflow = StateGraph(AuroraState)
workflow.add_node("agent", agent_node)
workflow.add_node("policy_gateway", policy_gateway_node)

if safe_tool_node:
    workflow.add_node("safe_tools", safe_tool_node)
    workflow.add_edge("safe_tools", "agent")
if sensitive_tool_node:
    workflow.add_node("sensitive_tools", sensitive_tool_node)
    workflow.add_edge("sensitive_tools", "agent")

workflow.add_conditional_edges("agent", should_continue_to_gateway, {"policy_gateway": "policy_gateway", END: END})

route_map = {"agent": "agent", "safe_tools": "safe_tools", "sensitive_tools": "sensitive_tools"}
workflow.add_conditional_edges("policy_gateway", route_from_gateway, route_map)

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
