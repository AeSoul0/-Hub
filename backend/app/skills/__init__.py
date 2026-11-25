"""
@file backend/app/skills/__init__.py
@description The skill package: each module exposes a BaseSkill that the registry loads.
"""

from .base import BaseSkill, SkillMetadata
from .registry import SkillRegistry, skill_registry

__all__ = ["BaseSkill", "SkillMetadata", "SkillRegistry", "skill_registry"]
