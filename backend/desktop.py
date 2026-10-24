"""
@file backend/desktop.py
@description The desktop app's sidecar (roadmap M14, ADR-020).

The Tauri shell starts this process with a pipe on stdin and stdout:

1. secrets from the OS keyring (login key and database password are
   created on first start, provider keys come from the Settings page);
2. the bundled Postgres + pgvector cluster, on 127.0.0.1 and a free port;
3. the API with the exported frontend, on 127.0.0.1 and another free port,
   with in-process events and cache instead of Redis;
4. one JSON line on stdout: {"event": "ready", "url": ".../desktop/launch/<token>"}.
   The window opens that URL; the token is good once.

When stdin closes (the window was closed, or the shell died) the API stops
and so does Postgres. Errors before "ready" are one JSON line too:
{"event": "error", "message": ...}, and the exit code is 1.

    python desktop.py [--data-dir DIR] [--pg-bin DIR] [--frontend-dir DIR]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import secrets as token_source
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional


BACKEND_DIR = Path(__file__).resolve().parent
DB_PASSWORD_KEY = "AEHUB_DESKTOP_DB_PASSWORD"


def emit(event: str, **fields: object) -> None:
    """
    One JSON line for the shell; everything else goes to stderr.
    """
    sys.__stdout__.write(json.dumps({"event": event, **fields}) + "\n")
    sys.__stdout__.flush()


def default_data_dir() -> Path:
    if os.getenv("AEHUB_DATA_DIR"):
        return Path(os.environ["AEHUB_DATA_DIR"])

    if sys.platform == "win32" and os.getenv("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "AEHub"

    return Path.home() / ".local" / "share" / "aehub"


def default_workspace() -> Path:
    documents = Path.home() / "Documents"

    return (documents if documents.is_dir() else Path.home()) / "AEHub"


def load_launcher() -> ModuleType:
    """
    The keyring code of `scripts/aehub.py`, shared with the Docker launcher:
    next to this file in the installed app, under scripts/ in the repo.
    """
    candidates = [
        os.getenv("AEHUB_LAUNCHER", ""),
        str(BACKEND_DIR / "aehub_launcher.py"),
        str(BACKEND_DIR.parent / "scripts" / "aehub.py"),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            spec = importlib.util.spec_from_file_location("aehub_launcher", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    raise RuntimeError("The ÆHub launcher (aehub.py) is missing from this installation.")


def secret(store, key: str) -> str:
    """
    The value of a generated secret, created on first start.
    """
    value = store.get(key)

    if not value:
        value = token_source.token_urlsafe(32)
        store.set(key, value)

    return value


def desktop_environment(
    store,
    secret_names,
    postgres_url: str,
    api_port: int,
    frontend_dir: Optional[Path],
    base: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    The API's environment. The user's own environment wins for the folder
    and the embedder; the database, events and origin are always ours.
    """
    env = dict(os.environ if base is None else base)

    for key in secret_names:
        value = store.get(key)
        if value:
            env[key] = value

    env.setdefault("AEHUB_ALLOWED_DIRS", str(default_workspace()))
    # ADR-020, point 9: no torch in the desktop app until the embedder is decided.
    env.setdefault("AEHUB_EMBEDDER", "hash")

    origin = f"http://127.0.0.1:{api_port}"
    env.update(
        {
            "POSTGRES_URL": postgres_url,
            "REDIS_URL": "memory://",
            "AEHUB_EVENT_BUS": "memory",
            "FRONTEND_URL": origin,
            "AEHUB_HOST": "127.0.0.1",
            "ENVIRONMENT": "desktop",
        }
    )

    if frontend_dir is not None:
        env["AEHUB_FRONTEND_DIR"] = str(frontend_dir)

    return env


def watch_stdin(on_close) -> threading.Thread:
    """
    Call on_close when the shell closes our stdin (or dies).
    """

    def read_until_eof() -> None:
        try:
            while sys.stdin.readline():
                pass
        finally:
            on_close()

    thread = threading.Thread(target=read_until_eof, name="aehub-stdin", daemon=True)
    thread.start()
    return thread


def serve(api_port: int, token_url: str, frontend_ready: bool) -> None:
    import uvicorn

    sys.path.insert(0, str(BACKEND_DIR))
    from main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=api_port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    def stop() -> None:
        server.should_exit = True

    async def announce() -> None:
        while not server.started:
            if server.should_exit:
                return
            await asyncio.sleep(0.05)
        emit("ready", url=token_url, port=api_port, frontend=frontend_ready)

    async def main() -> None:
        watch_stdin(stop)
        announcer = asyncio.create_task(announce())
        await server.serve()
        announcer.cancel()

    asyncio.run(main())


def run(args: argparse.Namespace) -> int:
    # stdout is the shell's channel: prints of the app go to stderr.
    sys.stdout = sys.stderr

    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    launcher = load_launcher()
    store = launcher.open_store()
    launcher.ensure_login_key(store)

    sys.path.insert(0, str(BACKEND_DIR))
    from app.desktop.postgres import EmbeddedPostgres, find_bin_dir, free_port

    postgres = EmbeddedPostgres(
        bin_dir=find_bin_dir(args.pg_bin),
        data_dir=data_dir / "pgdata",
        password=secret(store, DB_PASSWORD_KEY),
    )
    postgres.start()

    try:
        api_port = free_port()
        frontend_dir = Path(args.frontend_dir) if args.frontend_dir else BACKEND_DIR.parent / "frontend" / "out"
        frontend_ready = (frontend_dir / "index.html").is_file()

        os.environ.update(
            desktop_environment(
                store,
                launcher.SECRETS,
                postgres.url(),
                api_port,
                frontend_dir if frontend_ready else None,
            )
        )
        Path(os.environ["AEHUB_ALLOWED_DIRS"].split(os.pathsep)[0]).mkdir(parents=True, exist_ok=True)

        from app.desktop.launch import enable, issue_launch_token

        enable(store)
        token = issue_launch_token()
        serve(api_port, f"http://127.0.0.1:{api_port}/desktop/launch/{token}", frontend_ready)
    finally:
        postgres.stop()

    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="ÆHub desktop sidecar")
    parser.add_argument("--data-dir", help="cluster and logs (default: per-user app data)")
    parser.add_argument("--pg-bin", help="folder with initdb and pg_ctl")
    parser.add_argument("--frontend-dir", help="exported frontend (default: ../frontend/out)")
    args = parser.parse_args(argv)

    try:
        return run(args)
    except Exception as error:  # reported to the shell, which shows it
        emit("error", message=str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
