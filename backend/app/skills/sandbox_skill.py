"""
@file backend/app/skills/sandbox_skill.py
@description Native isolated execution skill for A.U.R.O.R.A.

Provides controlled Python and shell execution through the existing sandbox
manager. The skill exposes regular Python callables and does not depend on
an external tool-decorator framework.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from app.workers.sandbox import sandbox_manager

from .base import (
    BaseSkill,
    RiskLevel,
    SkillMetadata,
    ToolMetadata,
)


# ==============================================================================
# PYTHON SANDBOX TOOL
# ==============================================================================


async def execute_python_code(code: str) -> str:
    """
    Execute Python code inside the isolated sandbox.
    """
    result = await sandbox_manager.execute_python(
        code,
    )

    if result.exit_code == 0:
        return (
            "Output:\n"
            f"{result.stdout}"
        )

    return (
        f"Execution failed (exit code {result.exit_code}):\n"
        f"Stdout:\n{result.stdout}\n"
        f"Stderr:\n{result.stderr}"
    )


# ==============================================================================
# SHELL SANDBOX TOOL
# ==============================================================================


async def execute_shell_script(command: str) -> str:
    """
    Execute a shell command inside the isolated sandbox.
    """
    result = await sandbox_manager.execute_shell(
        command,
    )

    if result.exit_code == 0:
        return (
            "Output:\n"
            f"{result.stdout}"
        )

    return (
        f"Command failed (exit code {result.exit_code}):\n"
        f"Stdout:\n{result.stdout}\n"
        f"Stderr:\n{result.stderr}"
    )


# ==============================================================================
# SANDBOX SKILL
# ==============================================================================


class SandboxSkill(BaseSkill):
    """
    Provides isolated code and shell execution capabilities.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return the sandbox skill metadata.
        """
        return SkillMetadata(
            name="sandbox",
            description=(
                "Provides isolated Python and shell execution through "
                "the A.U.R.O.R.A. sandbox manager."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return the executable sandbox tools.
        """
        return [
            execute_python_code,
            execute_shell_script,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return security and execution metadata for sandbox tools.
        """
        return {
            "execute_python_code": ToolMetadata(
                name="execute_python_code",
                description=(
                    "Execute Python code in an isolated sandbox."
                ),
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                permissions_required=[],
                network_access=False,
                filesystem_access=False,
                max_runtime=30,
                max_output=10_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                        }
                    },
                    "required": ["code"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="python",
                audit_policy="standard",
            ),
            "execute_shell_script": ToolMetadata(
                name="execute_shell_script",
                description=(
                    "Execute a shell command in the isolated sandbox."
                ),
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                permissions_required=[],
                network_access=False,
                filesystem_access=False,
                max_runtime=30,
                max_output=10_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                        }
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="shell",
                audit_policy="standard",
            ),
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return sandbox-specific system instructions.
        """
        return (
            "You have access to an isolated execution sandbox. "
            "Use 'execute_python_code' for calculations, data processing, "
            "or controlled code execution. Use 'execute_shell_script' only "
            "when shell execution is necessary. Shell execution requires "
            "explicit approval and sandbox policy enforcement."
        )


def get_skill() -> BaseSkill:
    """
    Create the sandbox skill instance.
    """
    return SandboxSkill()