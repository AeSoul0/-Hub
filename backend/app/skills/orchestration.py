"""
@file backend/app/skills/orchestration.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.skills import skill_registry
from app.agents.subagents.base import SubagentFactory

class DelegateTaskInput(BaseTool):
    """Input for DelegateTaskTool"""
    task_description: str = Field(description="The specific task or question you want the subagent to resolve.")
    role_name: str = Field(description="The role name for the subagent, e.g., 'Researcher', 'Data Analyst'.")

class DelegateTaskTool(BaseTool):
    name: str = "delegate_task_to_subagent"
    description: str = "Delegates a complex, specialized, or multi-step task to an autonomous subagent. Use this when you need deep research, extensive code analysis, or specialized processing that requires its own focus."
    args_schema: Type[BaseModel] = DelegateTaskInput

    async def _arun(self, task_description: str, role_name: str) -> str:
        # Define a specific prompt based on role
        system_prompt = f"You are a highly specialized {role_name}. Your sole objective is to solve the following task assigned to you by the A.U.R.O.R.A. Orchestrator. Return only the final precise answer or data requested. Do not converse."
        
        # In a real scenario, we could map roles to specific toolsets.
        # For now, we give them the same safe tools as the orchestrator, minus orchestration tools to prevent infinite loops.
        safe_tools = [t for t in skill_registry.get_all_tools() if t.name != self.name]
        
        try:
            compiled_graph = SubagentFactory.create_subagent(
                role_name=role_name,
                system_prompt=system_prompt,
                tools=safe_tools
            )
            result = await SubagentFactory.run_subagent(compiled_graph, task_description)
            return f"Subagent [{role_name}] completed the task:\n{result}"
        except Exception as e:
            return f"Failed to delegate task to subagent. Error: {str(e)}"

    def _run(self, *args, **kwargs) -> str:
        raise NotImplementedError("DelegateTaskTool must be run asynchronously.")

skill_registry.register_tool(DelegateTaskTool(), requires_approval=False)
