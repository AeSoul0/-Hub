"""
@file backend/app/skills/supervisor_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import List, Callable, Dict, Optional
from langchain_core.tools import tool
from .base import BaseSkill, SkillMetadata, ToolMetadata, RiskLevel
from app.agents.subagents.base import SubagentFactory
from app.skills.web_search import perform_web_search

# Define standard subagents
RESEARCHER_PROMPT = (
    "You are a specialized Research Subagent. Your goal is to deeply investigate the user's task using web search. "
    "Be exhaustive, analyze multiple sources, and return a comprehensive summary of your findings. "
    "Do not stop at the first result if the topic requires deep context."
)

research_agent = SubagentFactory.create_subagent(
    role_name="Researcher",
    system_prompt=RESEARCHER_PROMPT,
    tools=[perform_web_search]
)

@tool
async def delegate_to_researcher(task: str) -> str:
    """
    Delega un task di ricerca complessa al Subagent 'Researcher'.
    Usa questo tool quando devi fare ricerche approfondite che richiedono tempo e analisi di più fonti.
    """
    print(f"[Supervisor] Delegating to Researcher: {task}")
    result = await SubagentFactory.run_subagent(research_agent, task)
    return f"Research Results:\n{result}"

class SupervisorSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="supervisor",
            description="Grants A.U.R.O.R.A. the ability to delegate tasks to specialized subagents.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        return [delegate_to_researcher]
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "delegate_to_researcher": ToolMetadata(
                name="delegate_to_researcher",
                description="Delega compiti di ricerca.",
                risk_level=RiskLevel.LOW
            )
        }
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        return (
            "You are acting as a Supervisor. If a request is extremely complex or requires "
            "deep, exhaustive research, DO NOT try to answer it yourself immediately. "
            "Instead, delegate the task to the appropriate Subagent using the delegation tools. "
            "Synthesize the subagent's response and present it clearly to the user."
        )

def get_skill() -> BaseSkill:
    return SupervisorSkill()
