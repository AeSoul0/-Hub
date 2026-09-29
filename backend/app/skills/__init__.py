"""
@file backend/app/skills/__init__.py
@description Core module for A.U.R.O.R.A. System

Implements core logic and architectural definitions.
"""

from .base import BaseSkill, SkillMetadata
from .registry import SkillRegistry, skill_registry

__all__ = ["BaseSkill", "SkillMetadata", "SkillRegistry", "skill_registry"]
