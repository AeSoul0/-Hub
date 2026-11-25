"""
@file backend/app/desktop/postgres.py
@description The Postgres + pgvector cluster of the desktop app (ADR-020).

The installer ships the server binaries; this module owns the cluster:
`initdb` on first start (scram-sha-256, random password from the OS keyring),
`pg_ctl start` on 127.0.0.1 and a free port, `pg_ctl stop` on exit. A
`postmaster.pid` left by a crash is removed when no server owns it.

The server listens only on loopback and has no Unix socket, so the password
is the only way in for other local accounts.
"""

from __future__ import annotations

import os
import socket
import subprocess  # nosec B404 - runs the bundled Postgres binaries only
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote


USER = "aehub"
DATABASE = "aehub"
START_TIMEOUT_SECONDS = 60


class PostgresError(RuntimeError):
    pass


def free_port() -> int:
    """
    A port nobody listens on right now. Another process could take it before
    Postgres binds it; `start` then fails with a clear error.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def find_bin_dir(explicit: Optional[str] = None) -> Path:
    """
    The folder holding initdb, pg_ctl and postgres: AEHUB_PG_BIN, the copy
    next to the installed app, or the first one on PATH.
    """
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates: List[Path] = []

    for value in (explicit, os.getenv("AEHUB_PG_BIN")):
        if value:
            candidates.append(Path(value))

    candidates.append(Path(sys.prefix).parent / "postgres" / "bin")

    for folder in os.getenv("PATH", "").split(os.pathsep):
        if folder:
            candidates.append(Path(folder))

    for folder in candidates:
        if (folder / f"initdb{suffix}").is_file() and (folder / f"pg_ctl{suffix}").is_file():
            return folder

    raise PostgresError(
        "PostgreSQL binaries not found: set AEHUB_PG_BIN to the folder with initdb and pg_ctl."
    )


@dataclass
class EmbeddedPostgres:
    bin_dir: Path
    data_dir: Path
    password: str
    port: int = 0

    def _exe(self, name: str) -> str:
        suffix = ".exe" if sys.platform == "win32" else ""
        return str(self.bin_dir / f"{name}{suffix}")

    def _run(self, args: List[str], timeout: int = START_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
        # The server must not inherit the console of the app: on Windows a
        # console window would open for every child.
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        return subprocess.run(  # nosec B603 - fixed binaries, no shell
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=flags,
            check=False,
        )

    def _grant_current_user(self, folder: Path) -> None:
        """
        Run as an administrator, initdb and pg_ctl restart themselves with a
        restricted token that drops the Administrators group, and on Windows
        files an administrator creates can be owned by that group. An explicit
        grant to this account keeps the folder readable by the server.
        """
        if sys.platform != "win32":
            return

        account = os.getenv("USERNAME", "")
        domain = os.getenv("USERDOMAIN", "")
        if not account:
            return

        self._run(["icacls", str(folder), "/grant", f"{domain}\\{account}:(OI)(CI)F" if domain else f"{account}:(OI)(CI)F"])

    @property
    def log_file(self) -> Path:
        return self.data_dir.parent / "postgres.log"

    def initialized(self) -> bool:
        return (self.data_dir / "PG_VERSION").is_file()

    def init(self) -> None:
        """
        Create the cluster: superuser `aehub` with the password, loopback only.
        """
        self.data_dir.parent.mkdir(parents=True, exist_ok=True)
        self._grant_current_user(self.data_dir.parent)
        password_file = self.data_dir.parent / ".pgpass-init"
        password_file.write_text(self.password, encoding="utf-8")

        try:
            os.chmod(password_file, 0o600)
            result = self._run(
                [
                    self._exe("initdb"),
                    "-D", str(self.data_dir),
                    "-U", USER,
                    "--auth=scram-sha-256",
                    f"--pwfile={password_file}",
                    "--encoding=UTF8",
                    "--no-locale",
                ]
            )
        finally:
            password_file.unlink(missing_ok=True)

        if result.returncode != 0:
            raise PostgresError(f"initdb failed: {result.stderr.strip() or result.stdout.strip()}")

        # No Unix socket and no network interface but loopback.
        with open(self.data_dir / "postgresql.conf", "a", encoding="utf-8") as conf:
            conf.write(
                "\n# ÆHub desktop (ADR-020)\n"
                "listen_addresses = '127.0.0.1'\n"
                "unix_socket_directories = ''\n"
            )

    def running(self) -> bool:
        result = self._run([self._exe("pg_ctl"), "status", "-D", str(self.data_dir)], timeout=15)
        return result.returncode == 0

    def _clear_stale_pid(self) -> None:
        pid_file = self.data_dir / "postmaster.pid"

        if pid_file.exists() and not self.running():
            pid_file.unlink()

    def start(self) -> None:
        if not self.initialized():
            self.init()

        self._clear_stale_pid()

        if self.running():
            raise PostgresError(
                f"Another Postgres server already uses {self.data_dir}: is ÆHub already open?"
            )

        if not self.port:
            self.port = free_port()

        # pg_ctl's output goes to a file, not a pipe: the server it spawns
        # inherits the handles, and a pipe would stay open until it exits.
        output_file = self.data_dir.parent / "pg_ctl.log"

        with open(output_file, "w", encoding="utf-8") as output:
            returncode = subprocess.run(  # nosec B603 - fixed binaries, no shell
                [
                    self._exe("pg_ctl"),
                    "start",
                    "-D", str(self.data_dir),
                    "-l", str(self.log_file),
                    "-w",
                    "-t", str(START_TIMEOUT_SECONDS),
                    "-o", f"-p {self.port}",
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=START_TIMEOUT_SECONDS + 10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            ).returncode

        if returncode != 0:
            raise PostgresError(
                f"Postgres did not start (see {self.log_file}): "
                f"{output_file.read_text(encoding='utf-8', errors='replace').strip()}"
            )

        self._ensure_database()

    def _ensure_database(self) -> None:
        import psycopg2

        connection = psycopg2.connect(self.url(database="postgres"))

        try:
            connection.autocommit = True

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))

                if cursor.fetchone() is None:
                    cursor.execute(f'CREATE DATABASE "{DATABASE}"')
        finally:
            connection.close()

    def stop(self) -> None:
        if self.initialized() and self.running():
            self._run(
                [self._exe("pg_ctl"), "stop", "-D", str(self.data_dir), "-m", "fast", "-w"],
                timeout=START_TIMEOUT_SECONDS,
            )

    def url(self, database: str = DATABASE) -> str:
        return f"postgresql://{USER}:{quote(self.password, safe='')}@127.0.0.1:{self.port}/{database}"


__all__ = ["EmbeddedPostgres", "PostgresError", "find_bin_dir", "free_port"]
