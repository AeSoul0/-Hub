"""
@file tests/test_skills.py
@description Unit tests for the native A.U.R.O.R.A. SkillRegistry.

The tests validate registration, public lookup APIs, executable tool
resolution, duplicate protection, and metadata preservation.
"""

from __future__ import annotations

from typing import Callable, Dict, List

import pytest

from app.skills.base import (
    BaseSkill,
    SkillMetadata,
    ToolMetadata,
)
from app.skills.registry import SkillRegistry


# ==============================================================================
# TEST SKILL
# ==============================================================================


def dummy_tool(
    value: str,
) -> str:
    """
    Return deterministic output for registry tests.
    """
    return value


class DummySkill(BaseSkill):
    """
    Minimal skill implementation used to test registry contracts.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return deterministic test skill metadata.
        """
        return SkillMetadata(
            name="dummy_skill",
            description="A dummy skill for registry testing.",
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return the dummy executable tool.
        """
        return [
            dummy_tool,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return metadata matching the executable tool.
        """
        return {
            "dummy_tool": ToolMetadata(
                name="dummy_tool",
                description="Deterministic test tool.",
            )
        }


# ==============================================================================
# REGISTRATION TESTS
# ==============================================================================


def test_skill_registry_registration() -> None:
    """
    Verify a valid skill can be registered and retrieved publicly.
    """
    registry = SkillRegistry()

    skill = DummySkill()

    registry.register_skill(skill)

    assert registry.get_skill("dummy_skill") is skill
    assert registry.get_registered_skill_names() == [
        "dummy_skill",
    ]


def test_skill_registry_resolves_tool_and_metadata() -> None:
    """
    Verify executable tool and metadata are resolved together.
    """
    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    resolved = registry.resolve_tool(
        "dummy_tool"
    )

    assert resolved is not None

    tool, metadata = resolved

    assert tool is dummy_tool
    assert metadata.name == "dummy_tool"
    assert metadata.description == "Deterministic test tool."


def test_skill_registry_public_metadata_lookup() -> None:
    """
    Verify metadata is exposed through the public API.
    """
    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    metadata = registry.get_tool_metadata(
        "dummy_tool"
    )

    assert metadata is not None
    assert metadata.name == "dummy_tool"


def test_skill_registry_get_tools() -> None:
    """
    Verify registered executable tools are returned.
    """
    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    tools = registry.get_all_tools()

    assert tools == [
        dummy_tool,
    ]


def test_skill_registry_unknown_tool_fails_closed() -> None:
    """
    Verify unknown tools are not resolved.
    """
    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    assert registry.get_tool(
        "unknown_tool"
    ) is None

    assert registry.get_tool_metadata(
        "unknown_tool"
    ) is None

    assert registry.resolve_tool(
        "unknown_tool"
    ) is None


def test_skill_registry_rejects_duplicate_skill() -> None:
    """
    Verify duplicate skill names cannot silently overwrite a registration.
    """
    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.register_skill(
            DummySkill()
        )


def test_skill_registry_rejects_duplicate_tool() -> None:
    """
    Verify duplicate tool names cannot silently overwrite a registration.
    """
    class OtherSkill(DummySkill):
        @property
        def metadata(self) -> SkillMetadata:
            return SkillMetadata(
                name="other_skill",
                description="Second test skill.",
            )

    registry = SkillRegistry()

    registry.register_skill(
        DummySkill()
    )

    with pytest.raises(
        ValueError,
        match="Tool 'dummy_tool' is already registered",
    ):
        registry.register_skill(
            OtherSkill()
        )