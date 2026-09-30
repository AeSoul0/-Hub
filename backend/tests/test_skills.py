"""
@file backend/tests/test_skills.py
@description Core module for A.U.R.O.R.A. System

Implements core logic and architectural definitions.
"""

from app.skills.base import BaseSkill
from app.skills.base import BaseSkill, SkillMetadata
from app.skills.registry import SkillRegistry

class DummySkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="dummy_skill", description="A dummy skill for testing", version="1.0")
        
    @property
    def tools(self):
        return []
        
    def get_tool_metadata(self):
        return {}

def test_skill_registry_registration():
    registry = SkillRegistry()
    registry.register_skill(DummySkill())
    
    assert "dummy_skill" in registry._skills
    assert registry._skills["dummy_skill"].metadata.name == "dummy_skill"
    
def test_skill_registry_get_tools():
    registry = SkillRegistry()
    registry.register_skill(DummySkill())
    
    tools = registry.get_all_tools()
    assert isinstance(tools, list)
