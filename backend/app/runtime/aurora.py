import os
import json
import operator
from typing import TypedDict, Annotated, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from duckduckgo_search import DDGS

# Define the State for our Agentic System
class AuroraState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str
    current_intent: str

from app.skills import skill_registry
from app.memory.manager import AuroraMemoryManager
import app.skills.memory_skill as memory_skill_module

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
    
    base_system_prompt = "You are A.U.R.O.R.A. (Autonomous Uplink & Real-time Operations Robotic Assistant), a personal AI operating system. Be concise, act as the core orchestrator. Always respond in Italian unless requested otherwise."
    skill_extensions = skill_registry.get_system_prompt_extensions()
    
    final_prompt = base_system_prompt
    if memories_text:
        final_prompt += "\n\n" + memories_text
        
    if skill_extensions:
        final_prompt += "\n" + skill_extensions
        
    system_msg = {"role": "system", "content": final_prompt}
    
    # Prepend system message
    full_messages = [system_msg] + list(messages)
    
    response = await llm_with_tools.ainvoke(full_messages)
    return {"messages": [response]}

# Conditional edge
def should_continue(state: AuroraState):
    messages = state["messages"]
    last_message = messages[-1]
    
    # Count how many AI messages with tool calls exist in the state
    tool_calls_count = sum(1 for m in messages if hasattr(m, "tool_calls") and m.tool_calls)
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if tool_calls_count > 5:
            print("[Warning] Max tool calls reached. Forcing END.")
            return END
            
        # Check if any requested tool requires approval
        for tc in last_message.tool_calls:
            if any(t.name == tc["name"] for t in sensitive_tools):
                return "sensitive_tools"
        return "safe_tools"
    return END

# Build the Graph
workflow = StateGraph(AuroraState)
workflow.add_node("agent", agent_node)

if safe_tool_node:
    workflow.add_node("safe_tools", safe_tool_node)
    workflow.add_edge("safe_tools", "agent")
if sensitive_tool_node:
    workflow.add_node("sensitive_tools", sensitive_tool_node)
    workflow.add_edge("sensitive_tools", "agent")

if safe_tool_node or sensitive_tool_node:
    workflow.add_conditional_edges("agent", should_continue, {"safe_tools": "safe_tools", "sensitive_tools": "sensitive_tools", END: END})
else:
    workflow.add_edge("agent", END)

workflow.set_entry_point("agent")

_aurora_app = None
_pool = None

async def get_aurora_app():
    """Lazily initializes the LangGraph application with PostgreSQL Checkpointer."""
    global _aurora_app, _pool
    if _aurora_app is not None:
        return _aurora_app
        
    postgres_url = os.getenv("POSTGRES_URL", "postgresql://aehub_user:aehub_pass@localhost:5432/aehub_db")
    
    _pool = AsyncConnectionPool(
        conninfo=postgres_url,
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
