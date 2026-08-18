import pytest
from app.skills.base import BaseSkill
from app.skills.registry import SkillRegistry

class DummySkill(BaseSkill):
    name = "dummy_skill"
    description = "A dummy skill for testing"
    
    def get_tools(self):
        return []

def test_skill_registry_registration():
    registry = SkillRegistry()
    registry.register(DummySkill())
    
    assert "dummy_skill" in registry.skills
    assert registry.skills["dummy_skill"].name == "dummy_skill"
    
def test_skill_registry_get_tools():
    registry = SkillRegistry()
    registry.register(DummySkill())
    
    tools = registry.get_all_tools()
    assert isinstance(tools, list)
