"""
@file backend/app/skills/memory_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

# We need the session_id to use the memory manager.
# In Langchain, we can pass runtime config or use a global context var,
# but for simplicity, the tools will require session_id or infer it from a context var.
# Let's use contextvars for session_id.
import contextvars
from typing import Callable, Dict, List, Optional

from langchain_core.tools import tool

from app.memory.manager import AuroraMemoryManager

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata

current_session_id = contextvars.ContextVar("current_session_id", default="default-session")

@tool
def save_semantic_memory(fact: str) -> str:
    """
    Salva un dato, un fatto o un'informazione importante riguardante l'utente o il contesto.
    Usa questo strumento per ricordare dettagli che saranno utili in futuro (es. nome utente, progetti in corso).
    """
    session = current_session_id.get()
    manager = AuroraMemoryManager(session)
    try:
        manager.save_semantic(fact)
        return f"Semantic memory saved: {fact}"
    except Exception as e:
        return f"Failed to save semantic memory: {str(e)}"

@tool
def save_procedural_memory(rule: str) -> str:
    """
    Salva una preferenza dell'utente, una regola operativa o una procedura.
    Usa questo strumento quando l'utente ti chiede di comportarti in un certo modo o di ricordarti di fare qualcosa in un certo formato.
    """
    session = current_session_id.get()
    manager = AuroraMemoryManager(session)
    try:
        manager.save_procedural(rule)
        return f"Procedural memory saved: {rule}"
    except Exception as e:
        return f"Failed to save procedural memory: {str(e)}"

class MemorySkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="memory",
            description="Allows A.U.R.O.R.A. to persist semantic and procedural memories.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        return [save_semantic_memory, save_procedural_memory]
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "save_semantic_memory": ToolMetadata(
                name="save_semantic_memory",
                description="Stores semantic memory",
                risk_level=RiskLevel.LOW
            ),
            "save_procedural_memory": ToolMetadata(
                name="save_procedural_memory",
                description="Stores procedural memory",
                risk_level=RiskLevel.LOW
            )
        }
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        return (
            "You have access to a long-term Memory system. "
            "If the user shares personal facts, preferences, or explicitly asks you to remember something, "
            "use the memory tools to store it. Do not use memory tools for transient conversational context."
        )

def get_skill() -> BaseSkill:
    return MemorySkill()
