"""
@file scripts/demo.py
@description `make demo`: the First Milestone of the spec (6.8), end to end.

    Compose up -> real command -> stop on a HIGH tool -> approval from the
    UI -> outcome and cost visible.

Steps:
1. Creates the configuration on a clean machine: `.env` (database password)
   and `backend/.env` (session secret, model settings). Secrets are random
   and never printed; the model API key is asked once, without echo.
2. Starts PostgreSQL, Redis, backend and frontend with Docker Compose.
3. Logs in and sends a real command whose execution needs a HIGH tool
   (a shell command in the sandbox), so the run stops for approval.
4. Waits until you approve or deny it from http://localhost:3000.
5. Prints what happened and what it cost.

Only the Python standard library is used, so it runs before any backend
dependency is installed.
"""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = ROOT / ".env"
BACKEND_ENV = ROOT / "backend" / ".env"

API = "http://127.0.0.1:3002"
UI = "http://localhost:3000"
ORIGIN = "http://localhost:3000"

SERVICES = ["postgres", "redis", "backend", "frontend"]

DEMO_COMMAND = (
    "Use the execute_shell_script tool to run this command in the sandbox: "
    "echo 'Hello from ÆHub' && date -u. Then tell me what it printed."
)


# ==============================================================================
# CONFIGURATION
# ==============================================================================


def read_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}

    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def append_env(path: Path, values: Dict[str, str], note: str) -> None:
    if not values:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [] if not existing or existing.endswith("\n") else [""]
    lines.append(f"# {note}")
    lines.extend(f"{key}={value}" for key, value in values.items())
    path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def ask(prompt: str, secret: bool = False) -> str:
    while True:
        value = (getpass.getpass(prompt) if secret else input(prompt)).strip()

        if value:
            return value


def ensure_configuration() -> Dict[str, str]:
    """
    Fill in what a clean checkout lacks. Existing values are never changed.
    """
    root = read_env(ROOT_ENV)
    if "POSTGRES_PASSWORD" not in root:
        append_env(
            ROOT_ENV,
            {"POSTGRES_PASSWORD": secrets.token_urlsafe(24)},
            "Created by make demo: password of the local PostgreSQL container.",
        )
        print("  created .env with a random database password")

    backend = read_env(BACKEND_ENV)
    missing: Dict[str, str] = {}

    if "AEHUB_SECRET_KEY" not in backend:
        missing["AEHUB_SECRET_KEY"] = secrets.token_urlsafe(32)

    # Required by the settings loader; only the legacy voice path uses it.
    if "GROQ_API_KEY" not in backend:
        missing["GROQ_API_KEY"] = "not-configured"

    has_model = any(
        key in backend for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "AEHUB_MODEL_ROLES")
    )

    if not has_model:
        print(
            "\n  The demo needs a real model. Enter an OpenAI API key and two\n"
            "  different models: one implements, the other (the Critic) reviews.\n"
            "  (For OpenRouter or a local model, set AEHUB_MODEL_ROLES in\n"
            "  backend/.env instead and run make demo again.)\n"
        )
        missing["OPENAI_API_KEY"] = ask("  OPENAI_API_KEY (hidden): ", secret=True)
        missing["OPENAI_MODEL"] = ask("  Worker model (OPENAI_MODEL): ")
        missing["AEHUB_CHECKER_MODEL"] = ask("  Critic model, different from the worker: ")

    append_env(BACKEND_ENV, missing, "Created by make demo.")

    if missing:
        print(f"  added {', '.join(sorted(missing))} to backend/.env")

    return read_env(BACKEND_ENV)


# ==============================================================================
# HTTP
# ==============================================================================


class Client:
    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        content_type: str = "application/json",
        timeout: float = 30.0,
    ) -> Any:
        request = urllib.request.Request(
            API + path,
            data=body,
            method=method,
            headers={"Origin": ORIGIN, "Content-Type": content_type},
        )

        with self.opener.open(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")

        return json.loads(payload) if payload else None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post_json(self, path: str, data: Dict[str, Any], timeout: float = 30.0) -> Any:
        return self.request("POST", path, json.dumps(data).encode("utf-8"), timeout=timeout)

    def post_form(self, path: str, data: Dict[str, str], timeout: float = 30.0) -> Any:
        boundary = "aehub-demo-" + secrets.token_hex(8)
        parts = []

        for name, value in data.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            )

        parts.append(f"--{boundary}--\r\n")

        return self.request(
            "POST",
            path,
            "".join(parts).encode("utf-8"),
            content_type=f"multipart/form-data; boundary={boundary}",
            timeout=timeout,
        )


def wait_for_health(timeout: float) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(API + "/health", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass

        time.sleep(3)

    raise SystemExit(
        "  The backend did not become healthy. Check: docker compose logs backend"
    )


# ==============================================================================
# DEMO
# ==============================================================================


def compose(*args: str) -> None:
    command = ["docker", "compose", *args]
    print("  $ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def latest_run(client: Client, known: set) -> Optional[Dict[str, Any]]:
    for run in client.get("/api/runs/stats?days=1").get("runs", []):
        if run["run_id"] not in known:
            return run

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-build", action="store_true", help="reuse existing images")
    parser.add_argument("--timeout", type=float, default=900, help="seconds to wait for approval")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        print("Docker is required: https://docs.docker.com/get-docker/")
        return 1

    print("1/5 Configuration")
    backend_env = ensure_configuration()

    print("2/5 Starting the stack (the first build takes a while)")
    compose("up", "-d", *([] if args.no_build else ["--build"]), *SERVICES)
    wait_for_health(timeout=300)

    print("3/5 Sending a real command")
    client = Client()
    client.post_json("/api/auth/login", {"key": backend_env["AEHUB_SECRET_KEY"]})
    known = {run["run_id"] for run in client.get("/api/runs/stats?days=1").get("runs", [])}
    print(f"  > {DEMO_COMMAND}")

    try:
        answer = client.post_form(
            "/api/orchestrator/ask",
            {"text": DEMO_COMMAND},
            timeout=120,
        )
    except urllib.error.HTTPError as exc:
        print(f"  The command failed: HTTP {exc.code} {exc.read().decode('utf-8', 'replace')}")
        return 1

    print(f"  first response: {json.dumps(answer, ensure_ascii=False)[:300]}")

    pending = client.get("/api/approvals")

    if not pending:
        print(
            "  The run did not stop for approval: the model did not call the\n"
            "  HIGH tool. Run make demo again, or check the model settings."
        )
        return 1

    print("4/5 Stopped on a HIGH tool, waiting for a human")
    for request in pending:
        print(f"  tool {request.get('tool_name')} with {json.dumps(request.get('arguments'), ensure_ascii=False)}")
    print(f"  Approve or deny it at {UI}/control-plane/approvals")

    deadline = time.monotonic() + args.timeout
    while client.get("/api/approvals") and time.monotonic() < deadline:
        time.sleep(3)

    if client.get("/api/approvals"):
        print("  No decision in time: an undecided request expires as DENY.")

    print("5/5 Outcome and cost")
    run = None
    while time.monotonic() < deadline + 120:
        run = latest_run(client, known)
        if run and run["status"].lower() not in {"running", "waiting_approval"}:
            break
        time.sleep(3)

    if run is None:
        print("  No run found.")
        return 1

    print(f"  run {run['run_id']}: {run['status']}")
    print(
        f"  {run['model_calls']} model calls, {run['tool_calls']} tool calls, "
        f"{run['total_tokens']} tokens, cost ${run['cost']:.4f}"
    )
    print(f"  Details: {UI}/control-plane/runs")
    print("\n  Stop the stack with: docker compose down")

    return 0


if __name__ == "__main__":
    sys.exit(main())
