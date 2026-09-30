"""
@file backend/app/skills/sandbox_skill.py
@description Implements sandbox_skill.py. Core components: SandboxSkill.

This module manages the internal business logic for SandboxSkill.
It provides specialized functionality to handle: execute_python_code, execute_shell_script, metadata, tools, get_tool_metadata, system_prompt_extension, get_skill.
"""
from typing import Callable, Dict, List, Optional

from langchain_core.tools import tool

from app.workers.sandbox import sandbox_manager

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


@tool
async def execute_python_code(code: str) -> str:
    """
    Executes execute_python_code logic.
    """
    """
    Esegue codice Python 3.11 in un ambiente sandbox isolato, sicuro e usa-e-getta.
    Usa questo strumento per eseguire calcoli complessi, analizzare dati o testare algoritmi.
    Ritorna lo stdout, lo stderr e l'exit code dell'esecuzione.
    """
    # Execute python code in the sandbox manager
    result = await sandbox_manager.execute_python(code)
    # Return standard output on success
    if result.exit_code == 0:
        return f"Output:\n{result.stdout}"
    # Return standard output and error on failure
    return f"Execution Failed (Exit Code {result.exit_code}):\nStdout: {result.stdout}\nStderr: {result.stderr}"

@tool
async def execute_shell_script(command: str) -> str:
    """
    Executes execute_shell_script logic.
    """
    """
    Esegue un comando shell (bash) in un ambiente sandbox isolato, sicuro e usa-e-getta (senza rete).
    Usa questo strumento per manipolazione dati di base o utility Unix-like.
    """
    # Execute shell command in the sandbox manager
    result = await sandbox_manager.execute_shell(command)
    # Return standard output on success
    if result.exit_code == 0:
        return f"Output:\n{result.stdout}"
    # Return standard output and error on failure
    return f"Command Failed (Exit Code {result.exit_code}):\nStdout: {result.stdout}\nStderr: {result.stderr}"


class SandboxSkill(BaseSkill):
    """
    Represents the SandboxSkill entity and its core operations.
    """
    @property
    def metadata(self) -> SkillMetadata:
        """
        Executes metadata logic.
        """
        # Define the skill metadata
        return SkillMetadata(
            name="sandbox",
            description="Provides the agent with isolated code and shell execution capabilities.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        """
        Executes tools logic.
        """
        # Expose the available tools
        return [execute_python_code, execute_shell_script]
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Executes get_tool_metadata logic.
        """
        # Return specific metadata and risk levels for each tool
        return {
            "execute_python_code": ToolMetadata(
                name="execute_python_code",
                description="Esegue Python isolato.",
                risk_level=RiskLevel.MEDIUM, # Might require approval based on config
                requires_approval=False
            ),
            "execute_shell_script": ToolMetadata(
                name="execute_shell_script",
                description="Esegue Bash isolato.",
                risk_level=RiskLevel.HIGH, # Shell execution is high risk
                requires_approval=True
            )
        }
        
    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Executes system_prompt_extension logic.
        """
        # Provide prompt context for the LLM regarding how and when to use these tools
        return (
            "You have access to a secure Sandbox execution environment. "
            "Whenever you need to perform complex mathematical calculations, data analysis, "
            "or string manipulations that are better suited for code, write a python script "
            "and execute it using the `execute_python_code` tool instead of calculating mentally. "
            "If a command requires shell execution, use `execute_shell_script`, but note that "
            "network access is disabled for security reasons."
        )

def get_skill() -> BaseSkill:
    """
    Executes get_skill logic.
    """
    # Factory function to instantiate the skill
    return SandboxSkill()
