"""
@file backend/app/skills/base.py
@description Implements base.py. Core components: RiskLevel, ToolMetadata, SkillMetadata, BaseSkill.

This module manages the internal business logic for RiskLevel, ToolMetadata, SkillMetadata, BaseSkill.
It provides specialized functionality to handle: metadata, tools, get_tool_metadata, system_prompt_extension, get_permission_scopes.
"""
from enum import Enum
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """
    Represents the RiskLevel entity and its core operations.
    """
    LOW = "low"         # automatic
    MEDIUM = "medium"   # configurable
    HIGH = "high"       # approval required

class ToolMetadata(BaseModel):
    """
    Represents the ToolMetadata entity and its core operations.
    """
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    permissions_required: List[str] = []

class SkillMetadata(BaseModel):
    """
    Represents the SkillMetadata entity and its core operations.
    """
    name: str = Field(..., description="Unique identifier for the skill (e.g., 'browser', 'filesystem')")
    description: str = Field(..., description="Human-readable description of what this skill does")
    version: str = "1.0.0"
    author: str = "AeSoul"

class BaseSkill:
    """
    Represents the BaseSkill entity and its core operations.
    """
    """
    Abstract base class for A.U.R.O.R.A. Skills.
    A Skill is a modular capability that provides tools, context, and permissions.
    """
    
    @property
    def metadata(self) -> SkillMetadata:
        """
        Executes metadata logic.
        """
        """Must return the metadata defining this skill."""
        raise NotImplementedError
        
    @property
    def tools(self) -> List[Callable]:
        """
        Executes tools logic.
        """
        """Must return a list of LangChain @tool decorated functions."""
        return []
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Executes get_tool_metadata logic.
        """
        """Returns metadata for the tools, specifically risk levels."""
        return {}
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Executes system_prompt_extension logic.
        """
        """
        Optional additional instructions added to the core JARVIS system prompt 
        when this skill is active.
        """
        return None
        
    def get_permission_scopes(self) -> List[str]:
        """
        Executes get_permission_scopes logic.
        """
        """Returns the list of permissions required by this skill."""
        return []
