"""
@file backend/app/skills/sandbox_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Callable, Dict, List, Optional

from langchain_core.tools import tool

from app.workers.sandbox import sandbox_manager

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


@tool
async def execute_python_code(code: str) -> str:
    """
    Esegue codice Python 3.11 in un ambiente sandbox isolato, sicuro e usa-e-getta.
    Usa questo strumento per eseguire calcoli complessi, analizzare dati o testare algoritmi.
    Ritorna lo stdout, lo stderr e l'exit code dell'esecuzione.
    """
    result = await sandbox_manager.execute_python(code)
    if result.exit_code == 0:
        return f"Output:\n{result.stdout}"
    return f"Execution Failed (Exit Code {result.exit_code}):\nStdout: {result.stdout}\nStderr: {result.stderr}"

@tool
async def execute_shell_script(command: str) -> str:
    """
    Esegue un comando shell (bash) in un ambiente sandbox isolato, sicuro e usa-e-getta (senza rete).
    Usa questo strumento per manipolazione dati di base o utility Unix-like.
    """
    result = await sandbox_manager.execute_shell(command)
    if result.exit_code == 0:
        return f"Output:\n{result.stdout}"
    return f"Command Failed (Exit Code {result.exit_code}):\nStdout: {result.stdout}\nStderr: {result.stderr}"


class SandboxSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="sandbox",
            description="Provides the agent with isolated code and shell execution capabilities.",
            version="1.0.0"
        )
        
    @property
    def tools(self) -> List[Callable]:
        return [execute_python_code, execute_shell_script]
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
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
        return (
            "You have access to a secure Sandbox execution environment. "
            "Whenever you need to perform complex mathematical calculations, data analysis, "
            "or string manipulations that are better suited for code, write a python script "
            "and execute it using the `execute_python_code` tool instead of calculating mentally. "
            "If a command requires shell execution, use `execute_shell_script`, but note that "
            "network access is disabled for security reasons."
        )

def get_skill() -> BaseSkill:
    return SandboxSkill()
