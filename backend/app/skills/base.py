"""
@file backend/app/skills/base.py
@description Native skill and tool metadata contracts for A.U.R.O.R.A.

This module defines framework-agnostic skill metadata and executable tool
contracts. Skills expose regular Python callables; the AgentRuntime decides
how those callables are executed and does not require a specific LLM framework.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


# ==============================================================================
# SKILL METADATA
# ==============================================================================


class RiskLevel(str, Enum):
    """
    Defines the execution risk associated with a registered tool.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolMetadata(BaseModel):
    """
    Describes one executable tool exposed by a skill.

    Security-sensitive execution properties are part of the metadata contract
    so they can be propagated into the canonical ToolSpec without being lost.
    """

    name: str
    description: str

    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False

    permissions_required: List[str] = Field(
        default_factory=list,
    )

    network_access: bool = False
    filesystem_access: bool = False

    max_runtime: int = 30
    max_output: int = 4000
    max_cost: float = 0.0

    idempotent: bool = False

    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
    )
    output_schema: Dict[str, Any] = Field(
        default_factory=dict,
    )

    sandbox_profile: str = "default"
    audit_policy: str = "standard"


class SkillMetadata(BaseModel):
    """
    Describes an installed A.U.R.O.R.A. skill.
    """

    name: str = Field(
        ...,
        description="Unique identifier for the skill.",
    )

    description: str = Field(
        ...,
        description="Human-readable description of the skill.",
    )

    version: str = "1.0.0"
    author: str = "AeSoul"


# ==============================================================================
# BASE SKILL CONTRACT
# ==============================================================================


class BaseSkill:
    """
    Framework-agnostic base class for A.U.R.O.R.A. skills.

    A skill may expose:
    - executable Python callables;
    - tool metadata used by authorization;
    - additional system instructions;
    - permission requirements.

    The runtime does not assume that the callable is decorated by LangChain
    or any other external orchestration framework.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return the metadata describing this skill.
        """
        raise NotImplementedError(
            "BaseSkill subclasses must implement the metadata property."
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return the executable Python callables exposed by this skill.
        """
        return []

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return metadata for every executable tool exposed by the skill.

        The dictionary key must match the callable/tool name used by the
        SkillRegistry and AgentRuntime.
        """
        return {}

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return optional system-level instructions contributed by this skill.
        """
        return None

    def get_permission_scopes(self) -> List[str]:
        """
        Return the permission scopes required by the skill.
        """
        return []