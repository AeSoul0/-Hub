"""
@file backend/app/agents/subagents/base.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import operator
import os
from typing import Annotated, Callable, List, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode


class SubagentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    task: str

class SubagentFactory:
    """
    Creates specialized sub-graphs for specific roles.
    Subagents don't have direct access to memory or global checkpoints; 
    they execute a single task and return the result.
    """
    
    @staticmethod
    def create_subagent(role_name: str, system_prompt: str, tools: List[Callable]):
        from app.runtime.tool_gateway import ToolGateway, ToolInvocation, ToolSpec, RiskLevel
        from app.core.security import Principal, RoleEnum
        
        async def node_agent(state: SubagentState):
            from app.core.models import ModelRouter, ModelProvider
            llm = ModelRouter.get_model(provider=ModelProvider.GROQ, model_name="llama-3.2-90b-vision-preview", temperature=0.3)
            
            if tools:
                llm = llm.bind_tools(tools)
                
            messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
            response = await llm.ainvoke(messages)
            return {"messages": [response]}

        async def execute_tools_node(state: SubagentState):
            messages = state["messages"]
            last_message = messages[-1]
            principal = state.get("principal", Principal(id="system", role=RoleEnum.USER, workspace_id="default"))
            session_id = state.get("session_id", "subagent-session")
            
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
                        
                    spec = ToolSpec(
                        name=tool_name,
                        description=tool_instance.description,
                        risk_level=RiskLevel.LOW,
                        approval_required=False
                    )
                    
                    invocation = ToolInvocation(
                        tool_name=tool_name,
                        arguments=arguments,
                        principal=principal,
                        session_id=session_id,
                        spec=spec
                    )
                    
                    async def executor(**kwargs):
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
            
        def should_continue(state: SubagentState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END
            
        workflow = StateGraph(SubagentState)
        workflow.add_node("agent", node_agent)
        
        if tools:
            workflow.add_node("tools", execute_tools_node)
            workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
            workflow.add_edge("tools", "agent")
        else:
            workflow.add_edge("agent", END)
            
        workflow.set_entry_point("agent")
        return workflow.compile()

    @staticmethod
    async def run_subagent(compiled_graph, task: str) -> str:
        """Executes a subagent synchronously for a specific task and returns its final answer."""
        initial_state = {
            "messages": [HumanMessage(content=task)],
            "task": task
        }
        
        final_state = await compiled_graph.ainvoke(initial_state)
        # Return the final message content
        return final_state["messages"][-1].content
