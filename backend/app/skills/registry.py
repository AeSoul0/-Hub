"""
@file backend/app/skills/registry.py
@description Native skill discovery and tool registration registry.

The registry owns skill lifecycle, executable tool metadata, callable lookup,
and prompt-extension aggregation. Runtime consumers must use the public
accessors exposed here instead of reaching into private state.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseSkill, ToolMetadata


# ==============================================================================
# SKILL REGISTRY
# ==============================================================================


class SkillRegistry:
    """
    Registry for active A.U.R.O.R.A. skills and executable tools.

    The registry is deliberately framework-agnostic. Registered tools are
    ordinary Python callables and may be synchronous or asynchronous.
    """

    def __init__(self) -> None:
        """
        Initialize an empty registry.
        """
        self._skills: Dict[str, BaseSkill] = {}
        self._tool_metadata: Dict[str, ToolMetadata] = {}
        # Tool name -> name of the skill that declares it.
        self._tool_owner: Dict[str, str] = {}

    # ==========================================================================
    # REGISTRATION
    # ==========================================================================

    def register_skill(
        self,
        skill: BaseSkill,
    ) -> None:
        """
        Register a skill and all of its declared tool metadata.

        Duplicate skills and tools are rejected instead of silently replaced.
        """
        skill_name = skill.metadata.name

        if not skill_name:
            raise ValueError(
                "Skill name cannot be empty."
            )

        if skill_name in self._skills:
            raise ValueError(
                f"Skill '{skill_name}' is already registered."
            )

        metadata_map = skill.get_tool_metadata()

        for tool_name, metadata in metadata_map.items():
            if not tool_name:
                raise ValueError(
                    f"Skill '{skill_name}' declared an empty tool name."
                )

            if metadata.name != tool_name:
                raise ValueError(
                    f"Tool metadata key '{tool_name}' does not match "
                    f"metadata name '{metadata.name}'."
                )

            if tool_name in self._tool_metadata:
                raise ValueError(
                    f"Tool '{tool_name}' is already registered."
                )

        self._skills[skill_name] = skill

        for tool_name, metadata in metadata_map.items():
            self._tool_metadata[tool_name] = metadata
            self._tool_owner[tool_name] = skill_name

    def refresh_skill(
        self,
        skill_name: str,
    ) -> None:
        """
        Re-read the tools of a registered skill whose tools change while the
        application runs (imported SKILL.md skills, F5). The same checks as
        registration apply; on error nothing changes.
        """
        skill = self._skills.get(
            skill_name
        )

        if skill is None:
            raise ValueError(
                f"Skill '{skill_name}' is not registered."
            )

        metadata_map = skill.get_tool_metadata()

        for tool_name, metadata in metadata_map.items():
            if not tool_name or metadata.name != tool_name:
                raise ValueError(
                    f"Skill '{skill_name}' declared an invalid tool "
                    f"'{tool_name}'."
                )

            owner = self._tool_owner.get(
                tool_name
            )

            if owner is not None and owner != skill_name:
                raise ValueError(
                    f"Tool '{tool_name}' is already registered."
                )

        tool_metadata = {
            name: metadata
            for name, metadata in self._tool_metadata.items()
            if self._tool_owner.get(name) != skill_name
        }
        tool_owner = {
            name: owner
            for name, owner in self._tool_owner.items()
            if owner != skill_name
        }

        for tool_name, metadata in metadata_map.items():
            tool_metadata[tool_name] = metadata
            tool_owner[tool_name] = skill_name

        # Whole dicts are swapped, so a reader never sees half an update.
        self._tool_metadata = tool_metadata
        self._tool_owner = tool_owner

    # ==========================================================================
    # PACKAGE DISCOVERY
    # ==========================================================================

    def load_from_package(
        self,
        package_name: str = "app.skills",
    ) -> None:
        """
        Discover and register BaseSkill factories from a Python package.

        A module is considered a skill module only when it exposes a
        zero-argument `get_skill()` factory returning BaseSkill.
        """
        package = importlib.import_module(
            package_name
        )

        if not hasattr(
            package,
            "__path__",
        ):
            raise ValueError(
                f"Package '{package_name}' is not a package."
            )

        excluded_modules = {
            "base",
            "loader",
            "registry",
        }

        discovered_modules = sorted(
            pkgutil.iter_modules(
                package.__path__
            ),
            key=lambda item: item[1],
        )

        for _, module_name, is_package in discovered_modules:
            if (
                module_name in excluded_modules
                or is_package
            ):
                continue

            full_module_name = (
                f"{package_name}.{module_name}"
            )

            try:
                module = importlib.import_module(
                    full_module_name
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to import skill module "
                    f"'{full_module_name}'."
                ) from exc

            factory = getattr(
                module,
                "get_skill",
                None,
            )

            if factory is None:
                continue

            try:
                skill = factory()
            except Exception as exc:
                raise RuntimeError(
                    f"Skill factory '{full_module_name}.get_skill' "
                    "failed during initialization."
                ) from exc

            if not isinstance(
                skill,
                BaseSkill,
            ):
                raise TypeError(
                    f"Skill factory '{full_module_name}.get_skill' "
                    "did not return a BaseSkill instance."
                )

            self.register_skill(
                skill
            )

    # ==========================================================================
    # SKILL LOOKUP
    # ==========================================================================

    def get_skill(
        self,
        name: str,
    ) -> Optional[BaseSkill]:
        """
        Return a registered skill by name.
        """
        return self._skills.get(
            name
        )

    def get_registered_skill_names(self) -> List[str]:
        """
        Return registered skill names in deterministic order.
        """
        return sorted(
            self._skills
        )

    # ==========================================================================
    # TOOL LOOKUP
    # ==========================================================================

    def get_registered_tool_names(self) -> List[str]:
        """
        Return registered tool names in deterministic order.
        """
        return sorted(
            self._tool_metadata
        )

    def get_skill_tool_names(
        self,
        skill_name: str,
    ) -> List[str]:
        """
        The tools a skill declares, in deterministic order.
        """
        return sorted(
            name
            for name, owner in self._tool_owner.items()
            if owner == skill_name
        )

    def get_tool_metadata(
        self,
        tool_name: str,
    ) -> Optional[ToolMetadata]:
        """
        Return metadata for one registered tool.
        """
        return self._tool_metadata.get(
            tool_name
        )

    def get_tool(
        self,
        tool_name: str,
    ) -> Optional[Any]:
        """
        Return the executable implementation for a registered tool.

        The metadata registry is checked first so an implementation cannot
        become executable merely by being present on a Skill object, and
        only the skill that declared the tool is searched.
        """
        owner = self._tool_owner.get(
            tool_name
        )

        if tool_name not in self._tool_metadata or owner is None:
            return None

        # Only the skill that declared the tool may implement it.
        for tool in self._skills[owner].tools:
            candidate_name = (
                getattr(
                    tool,
                    "name",
                    None,
                )
                or getattr(
                    tool,
                    "__name__",
                    None,
                )
            )

            if candidate_name == tool_name:
                return tool

        return None

    def resolve_tool(
        self,
        tool_name: str,
    ) -> Optional[
        Tuple[Any, ToolMetadata]
    ]:
        """
        Resolve executable implementation and metadata atomically.
        """
        metadata = self.get_tool_metadata(
            tool_name
        )

        if metadata is None:
            return None

        tool = self.get_tool(
            tool_name
        )

        if tool is None:
            return None

        return (
            tool,
            metadata,
        )

    def get_all_tools(self) -> List[Any]:
        """
        Return all executable tools exposed by registered skills.
        """
        tools: List[Any] = []

        for skill_name in self.get_registered_skill_names():
            tools.extend(
                self._skills[
                    skill_name
                ].tools
            )

        return tools

    # ==========================================================================
    # PROMPT CONTEXT
    # ==========================================================================

    def get_system_prompt_extensions(self) -> str:
        """
        Return the combined system-prompt extensions from active skills.
        """
        extensions: List[str] = []

        for skill_name in self.get_registered_skill_names():
            skill = self._skills[
                skill_name
            ]

            extension = (
                skill.system_prompt_extension
            )

            if extension:
                extensions.append(
                    f"[{skill.metadata.name.upper()} SKILL]\n"
                    f"{extension}"
                )

        if not extensions:
            return ""

        return (
            "\n\n--- ACTIVE SKILLS CONTEXT ---\n"
            + "\n\n".join(
                extensions
            )
        )


# ==============================================================================
# APPLICATION REGISTRY
# ==============================================================================

skill_registry = SkillRegistry()