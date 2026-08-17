from typing import List, Callable, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "low"         # automatic
    MEDIUM = "medium"   # configurable
    HIGH = "high"       # approval required

class ToolMetadata(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    permissions_required: List[str] = []

class SkillMetadata(BaseModel):
    name: str = Field(..., description="Unique identifier for the skill (e.g., 'browser', 'filesystem')")
    description: str = Field(..., description="Human-readable description of what this skill does")
    version: str = "1.0.0"
    author: str = "AeSoul"

class BaseSkill:
    """
    Abstract base class for A.U.R.O.R.A. Skills.
    A Skill is a modular capability that provides tools, context, and permissions.
    """
    
    @property
    def metadata(self) -> SkillMetadata:
        """Must return the metadata defining this skill."""
        raise NotImplementedError
        
    @property
    def tools(self) -> List[Callable]:
        """Must return a list of LangChain @tool decorated functions."""
        return []
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """Returns metadata for the tools, specifically risk levels."""
        return {}
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Optional additional instructions added to the core JARVIS system prompt 
        when this skill is active.
        """
        return None
        
    def get_permission_scopes(self) -> List[str]:
        """Returns the list of permissions required by this skill."""
        return []
