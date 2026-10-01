"""
@file backend/app/workers/sandbox.py
@description Secure ephemeral Docker-based execution sandbox.
"""

import asyncio
from typing import Dict, Optional, Sequence

from pydantic import BaseModel


class SandboxResult(BaseModel):
    """
    Result returned by a sandbox execution.
    """

    stdout: str
    stderr: str
    exit_code: int
    artifacts: Dict[str, str] = {}


class EphemeralSandboxManager:
    """
    Manage isolated Python and shell execution through Docker.
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        network_disabled: bool = True,
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled

    async def _run_process(
        self,
        command: Sequence[str],
        timeout: int,
    ):
        """
        Execute a subprocess and deterministically clean up its pipes/process.

        The communication task is shielded from wait_for cancellation so that
        a timeout does not leave stdout/stderr transports alive after the
        event loop is closed.
        """
        process: Optional[asyncio.subprocess.Process] = None
        communication_task: Optional[
            asyncio.Task
        ] = None

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            communication_task = asyncio.create_task(
                process.communicate()
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    asyncio.shield(
                        communication_task
                    ),
                    timeout=timeout,
                )

                return (
                    stdout,
                    stderr,
                    process.returncode,
                    False,
                )

            except asyncio.TimeoutError:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass

                stdout, stderr = await communication_task

                return (
                    stdout,
                    stderr,
                    124,
                    True,
                )

        finally:
            if communication_task is not None:
                try:
                    if not communication_task.done():
                        await communication_task
                except Exception:
                    pass

            if process is not None:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass

                try:
                    await process.wait()
                except Exception:
                    pass

                # Give asyncio one scheduler turn to process the final
                # subprocess/pipe callbacks before the test event loop closes.
                await asyncio.sleep(0)

    async def execute_python(
        self,
        code: str,
        timeout: int = 30,
    ) -> SandboxResult:
        """
        Execute Python code inside an isolated Docker container.
        """
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--init",
            "-m",
            self.memory_limit,
            "--memory-swap",
            self.memory_limit,
            "--cpus",
            "0.5",
            "--pids-limit",
            "50",
            "--read-only",
            "--security-opt",
            "no-new-privileges",
            "--security-opt",
            "apparmor=docker-default",
            "--cap-drop=ALL",
            "--tmpfs",
            "/tmp:size=50M,exec,mode=1777",
            "--env",
            "PYTHONUNBUFFERED=1",
            self.image,
            "python",
            "-c",
            code,
        ]

        if self.network_disabled:
            cmd.insert(4, "--network")
            cmd.insert(5, "none")

        try:
            (
                stdout,
                stderr,
                exit_code,
                timed_out,
            ) = await self._run_process(
                cmd,
                timeout,
            )

            if timed_out:
                return SandboxResult(
                    stdout="",
                    stderr="Execution timed out.",
                    exit_code=124,
                )

            return SandboxResult(
                stdout=stdout.decode(
                    "utf-8",
                    errors="replace",
                ),
                stderr=stderr.decode(
                    "utf-8",
                    errors="replace",
                ),
                exit_code=exit_code,
            )

        except Exception as exc:
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox Error: {exc}",
                exit_code=1,
            )

    async def execute_shell(
        self,
        command: str,
        timeout: int = 30,
    ) -> SandboxResult:
        """
        Execute a shell command inside an isolated Docker container.
        """
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--init",
            "-m",
            self.memory_limit,
            "--memory-swap",
            self.memory_limit,
            "--cpus",
            "0.5",
            "--pids-limit",
            "50",
            "--read-only",
            "--security-opt",
            "no-new-privileges",
            "--security-opt",
            "apparmor=docker-default",
            "--cap-drop=ALL",
            "--tmpfs",
            "/tmp:size=50M,exec,mode=1777",
            self.image,
            "sh",
            "-c",
            command,
        ]

        if self.network_disabled:
            cmd.insert(4, "--network")
            cmd.insert(5, "none")

        try:
            (
                stdout,
                stderr,
                exit_code,
                timed_out,
            ) = await self._run_process(
                cmd,
                timeout,
            )

            if timed_out:
                return SandboxResult(
                    stdout="",
                    stderr="Execution timed out.",
                    exit_code=124,
                )

            return SandboxResult(
                stdout=stdout.decode(
                    "utf-8",
                    errors="replace",
                ),
                stderr=stderr.decode(
                    "utf-8",
                    errors="replace",
                ),
                exit_code=exit_code,
            )

        except Exception as exc:
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox Error: {exc}",
                exit_code=1,
            )


sandbox_manager = EphemeralSandboxManager()