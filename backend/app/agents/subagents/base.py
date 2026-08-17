import os
import operator
from typing import TypedDict, Annotated, Sequence, List, Callable
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
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
        
        tool_node = ToolNode(tools) if tools else None
        
        async def node_agent(state: SubagentState):
            llm = ChatGroq(
                model="llama3-70b-8192", 
                temperature=0.3, # Subagents should be more deterministic
                api_key=os.getenv("GROQ_API_KEY")
            )
            
            if tools:
                llm = llm.bind_tools(tools)
                
            messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
            response = await llm.ainvoke(messages)
            return {"messages": [response]}
            
        def should_continue(state: SubagentState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END
            
        workflow = StateGraph(SubagentState)
        workflow.add_node("agent", node_agent)
        
        if tool_node:
            workflow.add_node("tools", tool_node)
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
