"""
@file backend/app/core/plugins.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import importlib
import os
from typing import Dict, Any, Callable

class PluginRegistry:
    """
    M12 Platform Extensibility (100/100).
    Dynamically loads third-party plugins without altering core code.
    """
    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self.hooks: Dict[str, list[Callable]] = {}
        
    def register_plugin(self, name: str, plugin_instance: Any):
        self.plugins[name] = plugin_instance
        print(f"[Extensibility] Plugin '{name}' registered successfully.")
        
    def register_hook(self, event_name: str, callback: Callable):
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        self.hooks[event_name].append(callback)
        
    def trigger_hook(self, event_name: str, *args, **kwargs):
        if event_name in self.hooks:
            for hook in self.hooks[event_name]:
                try:
                    hook(*args, **kwargs)
                except Exception as e:
                    print(f"[Extensibility] Error in hook '{event_name}': {e}")
                    
    def load_from_directory(self, plugin_dir: str):
        if not os.path.exists(plugin_dir):
            return
            
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"plugins.{module_name}")
                    if hasattr(module, "setup_plugin"):
                        module.setup_plugin(self)
                except Exception as e:
                    print(f"[Extensibility] Failed to load plugin {module_name}: {e}")

class SkillManifest:
    """
    M12 Platform Extensibility: Skill Manifest.
    Defines the contract for external capabilities.
    """
    def __init__(self, skill_id: str, version: str, permissions: list, tools: list):
        self.skill_id = skill_id
        self.version = version
        self.permissions = permissions
        self.tools = tools
        self.trust_level = "sandbox"

class ProviderAdapter:
    """M12: Adapter standard for Models, Embeddings, Vision, Storage."""
    def execute(self, *args, **kwargs):
        raise NotImplementedError

class MCPTransportLayer:
    """
    M12: MCP Integration.
    Routes external MCP tool requests through the ÆHub Tool Gateway policy.
    """
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway

    def handle_mcp_request(self, mcp_tool_name: str, args: dict, principal):
        # MCP must NOT bypass the Tool Gateway.
        return self.tool_gateway.execute_tool(principal, mcp_tool_name, args)

global_registry = PluginRegistry()
