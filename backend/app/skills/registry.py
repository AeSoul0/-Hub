"""
@file backend/app/skills/registry.py
@description Implements registry.py. Core components: SkillRegistry.

This module manages the internal business logic for SkillRegistry.
It provides specialized functionality to handle: register_skill, load_from_package, get_all_tools, get_system_prompt_extensions.
"""
import importlib
import pkgutil
from typing import Dict, List

from .base import BaseSkill, ToolMetadata


class SkillRegistry:
    """
    Represents the SkillRegistry entity and its core operations.
    """
    """
    Registry for managing all active A.U.R.O.R.A. skills.
    Handles discovery, loading, and capability extraction (tools/prompts).
    """
    
    def __init__(self):
        """
        Executes __init__ logic.
        """
        self._skills: Dict[str, BaseSkill] = {}
        self._tool_metadata: Dict[str, ToolMetadata] = {}
        
    def register_skill(self, skill: BaseSkill):
        """
        Executes register_skill logic.
        """
        """Registers an initialized skill instance."""
        name = skill.metadata.name
        if name in self._skills:
            print(f"[Warning] Skill '{name}' is already registered. Overwriting.")
        self._skills[name] = skill
        
        # Merge tool metadata
        for tool_name, metadata in skill.get_tool_metadata().items():
            self._tool_metadata[tool_name] = metadata
            
        print(f"[Skills] Registered '{name}' v{skill.metadata.version}")
        
    def load_from_package(self, package_name: str = "app.skills"):
        """
        Executes load_from_package logic.
        """
        """
        Dynamically loads all skill modules from the specified package.
        Assumes each module in the package exposes a 'get_skill()' function.
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            print(f"[Error] Failed to load skills package '{package_name}': {e}")
            return

        # Iterate through all submodules in the package
        if not hasattr(package, "__path__"):
            return
            
        for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
            # Skip base, loader, registry etc
            if module_name in ["base", "loader", "registry"] or is_pkg:
                continue
                
            full_module_name = f"{package_name}.{module_name}"
            try:
                module = importlib.import_module(full_module_name)
                if hasattr(module, "get_skill"):
                    skill_instance = module.get_skill()
                    if isinstance(skill_instance, BaseSkill):
                        self.register_skill(skill_instance)
            except Exception as e:
                print(f"[Error] Failed to load skill from {full_module_name}: {e}")

    def get_all_tools(self) -> List:
        """
        Executes get_all_tools logic.
        """
        """Returns an aggregated list of all @tool functions from all registered skills."""
        all_tools = []
        for skill in self._skills.values():
            all_tools.extend(skill.tools)
        return all_tools
        
    def get_system_prompt_extensions(self) -> str:
        """
        Executes get_system_prompt_extensions logic.
        """
        """Returns a concatenated string of all active skill prompt extensions."""
        extensions = []
        for skill in self._skills.values():
            ext = skill.system_prompt_extension
            if ext:
                extensions.append(f"[{skill.metadata.name.upper()} SKILL]\n{ext}")
        
        if not extensions:
            return ""
            
        return "\n\n--- ACTIVE SKILLS CONTEXT ---\n" + "\n\n".join(extensions)

# Global singleton registry
skill_registry = SkillRegistry()
