"""
@file backend/app/workers/sandbox.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import asyncio
from typing import Dict

from pydantic import BaseModel


class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    artifacts: Dict[str, str] = {}

class EphemeralSandboxManager:
    """
    Manages isolated code execution for A.U.R.O.R.A. agents.
    In a real LAN deployment, this would communicate with Docker Daemon via the Docker SDK
    or a remote execution worker to spawn an ephemeral container, execute the script, 
    collect the output and artifacts, and then destroy the container.
    """
    
    def __init__(self, image: str = "python:3.11-slim", memory_limit: str = "512m", network_disabled: bool = True):
        self.image = image
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled

    async def execute_python(self, code: str, timeout: int = 30) -> SandboxResult:
        """
        Executes Python code in a secure sandboxed environment.
        """
        cmd = [
            "docker", "run", "--rm", "-i",
            "-m", self.memory_limit,
            "--cpus", "0.5",
            "--pids-limit", "50",
            "--read-only",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp",
            "--env", "PYTHONUNBUFFERED=1",
            self.image,
            "python", "-c", code
        ]
        
        if self.network_disabled:
            cmd.insert(4, "--network")
            cmd.insert(5, "none")
            
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            
            return SandboxResult(
                stdout=stdout.decode("utf-8"),
                stderr=stderr.decode("utf-8"),
                exit_code=process.returncode
            )
        except asyncio.TimeoutError:
            # Attempt to kill if timed out
            try:
                process.kill()
            except Exception:
                pass
            return SandboxResult(
                stdout="",
                stderr="Execution timed out.",
                exit_code=124
            )
        except Exception as e:
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox Error: {str(e)}",
                exit_code=1
            )

    async def execute_shell(self, command: str, timeout: int = 30) -> SandboxResult:
        """
        Executes a shell command in a secure sandboxed environment.
        """
        cmd = [
            "docker", "run", "--rm", "-i",
            "-m", self.memory_limit,
            self.image,
            "sh", "-c", command
        ]
        
        if self.network_disabled:
            cmd.insert(4, "--network")
            cmd.insert(5, "none")
            
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            
            return SandboxResult(
                stdout=stdout.decode("utf-8"),
                stderr=stderr.decode("utf-8"),
                exit_code=process.returncode
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return SandboxResult(
                stdout="",
                stderr="Execution timed out.",
                exit_code=124
            )
        except Exception as e:
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox Error: {str(e)}",
                exit_code=1
            )

# Global singleton for sandbox orchestration
sandbox_manager = EphemeralSandboxManager()
