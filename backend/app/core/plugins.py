"""
@file backend/app/core/plugins.py
@description Implements plugins.py. Core components: PluginRegistry, SkillManifest, ProviderAdapter, MCPTransportLayer.

This module manages the internal business logic for PluginRegistry, SkillManifest, ProviderAdapter, MCPTransportLayer.
It provides specialized functionality to handle: register_plugin, register_hook, trigger_hook, load_from_directory, execute, handle_mcp_request.
"""
import importlib
import os
from typing import Dict, Any, Callable

class PluginRegistry:
    """
    Represents the PluginRegistry entity and its core operations.
    """
    """
    M12 Platform Extensibility (100/100).
    Dynamically loads third-party plugins without altering core code.
    """
    def __init__(self):
        """
        Executes __init__ logic.
        """
        self.plugins: Dict[str, Any] = {}
        self.hooks: Dict[str, list[Callable]] = {}
        
    def register_plugin(self, name: str, plugin_instance: Any):
        """
        Executes register_plugin logic.
        """
        # Store the plugin instance in the registry to make it accessible to the platform
        # Store the plugin instance in the registry to make it accessible to the platform
        self.plugins[name] = plugin_instance
        print(f"[Extensibility] Plugin '{name}' registered successfully.")
        
    def register_hook(self, event_name: str, callback: Callable):
        """
        Executes register_hook logic.
        """
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        self.hooks[event_name].append(callback)
        
    def trigger_hook(self, event_name: str, *args, **kwargs):
        """
        Executes trigger_hook logic.
        """
        # Execute all callback functions registered for the specified event
        # Execute all callback functions registered for the specified event
        if event_name in self.hooks:
            for hook in self.hooks[event_name]:
                try:
                    hook(*args, **kwargs)
                except Exception as e:
                    print(f"[Extensibility] Error in hook '{event_name}': {e}")
                    
    def load_from_directory(self, plugin_dir: str):
        """
        Executes load_from_directory logic.
        """
        # Dynamically import and setup all valid python modules found in the plugin directory
        # Dynamically import and setup all valid python modules found in the plugin directory
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
    Represents the SkillManifest entity and its core operations.
    """
    """
    M12 Platform Extensibility: Skill Manifest.
    Defines the contract for external capabilities.
    """
    def __init__(self, skill_id: str, version: str, permissions: list, tools: list):
        """
        Executes __init__ logic.
        """
        self.skill_id = skill_id
        self.version = version
        self.permissions = permissions
        self.tools = tools
        self.trust_level = "sandbox"

class ProviderAdapter:
    """
    Represents the ProviderAdapter entity and its core operations.
    """
    """M12: Adapter standard for Models, Embeddings, Vision, Storage."""
    def execute(self, *args, **kwargs):
        """
        Executes execute logic.
        """
        raise NotImplementedError

class MCPTransportLayer:
    """
    Represents the MCPTransportLayer entity and its core operations.
    """
    """
    M12: MCP Integration.
    Routes external MCP tool requests through the ÆHub Tool Gateway policy.
    """
    def __init__(self, tool_gateway):
        """
        Executes __init__ logic.
        """
        self.tool_gateway = tool_gateway

    def handle_mcp_request(self, mcp_tool_name: str, args: dict, principal):
        """
        Executes handle_mcp_request logic.
        """
        # MCP must NOT bypass the Tool Gateway. Route requests securely via Gateway policy.
        # MCP must NOT bypass the Tool Gateway. Route requests securely via Gateway policy.
        # MCP must NOT bypass the Tool Gateway.
        return self.tool_gateway.execute_tool(principal, mcp_tool_name, args)

global_registry = PluginRegistry()
