"""
@file scripts/demo.py
@description `make demo`: the First Milestone of the spec (6.8), end to end.

    Compose up -> real command -> stop on a HIGH tool -> approval from the
    UI -> outcome and cost visible.

Steps:
1. Creates the configuration on a clean machine through the launcher
   (scripts/aehub.py): database password in `.env`, login key and model API
   key in the OS keyring. Secrets are random or asked once without echo, and
   never printed.
2. Starts PostgreSQL, Redis, backend and frontend with Docker Compose, with
   the keys from the keyring.
3. Logs in, sets the Worker and Critic models through the Settings API if
   they are not configured yet, and sends a real command whose execution
   needs a HIGH tool (a shell command in the sandbox), so the run stops for
   approval.
4. Waits until you approve or deny it from http://localhost:3000.
5. Prints what happened and what it cost.

Only the Python standard library is used, so it runs before any backend
dependency is installed.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

import aehub


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


def ask(prompt: str, secret: bool = False) -> str:
    while True:
        value = aehub.prompt(prompt, secret)

        if value:
            return value


def ensure_configuration(store: aehub.SecretStore) -> None:
    """
    Fill in what a clean checkout lacks. Existing values are never changed.
    """
    if aehub.ensure_database_password():
        print("  created .env with a random database password")

    moved = aehub.migrate_env_secrets(store)
    if moved:
        print(f"  moved {', '.join(moved)} from backend/.env into the keyring")

    if aehub.ensure_login_key(store):
        print("  created the Control Plane login key in the keyring")

    if not aehub.has_model_key(store):
        print(
            "\n  The demo needs a real model. Enter an OpenAI API key; it goes to\n"
            f"  the OS keyring ({store.name}), not to a file.\n"
            "  (For OpenRouter, run python scripts/aehub.py setup instead.)\n"
        )
        store.set("OPENAI_API_KEY", ask("  OPENAI_API_KEY (hidden): ", secret=True))


def ensure_models(client: "Client") -> bool:
    """
    Worker and Critic models through the Settings API (M12), when the
    configuration would stop every run. Returns True when runs can start.
    """
    view = client.get("/api/settings")
    codes = {issue["code"] for issue in view["issues"] if issue["severity"] == "error"}

    if "routing_invalid" in codes:
        print(
            "\n  Choose two different models: one implements, the other (the Critic)\n"
            "  reviews. You can change them later in Settings.\n"
        )
        worker = ask("  Worker model (e.g. an OpenAI model id): ")
        critic = ask("  Critic model, different from the worker: ")

        try:
            view = client.request(
                "PUT",
                "/api/settings",
                json.dumps({"values": {"OPENAI_MODEL": worker, "AEHUB_CHECKER_MODEL": critic}}).encode("utf-8"),
            )
        except urllib.error.HTTPError as exc:
            print(f"  Settings refused: {exc.read().decode('utf-8', 'replace')}")
            return False

    errors = [issue["message"] for issue in view["issues"] if issue["severity"] == "error"]

    for message in errors:
        print(f"  ! {message}")

    return not errors


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
    try:
        store = aehub.open_store()
    except aehub.LauncherError as exc:
        print(exc)
        return 1

    ensure_configuration(store)

    print("2/5 Starting the stack (the first build takes a while)")
    aehub.up(store, build=not args.no_build, services=SERVICES)
    wait_for_health(timeout=300)

    print("3/5 Sending a real command")
    client = Client()
    client.post_json("/api/auth/login", {"key": store.get("AEHUB_SECRET_KEY")})

    if not ensure_models(client):
        print(f"  Fix the configuration at {UI}/control-plane/settings and run make demo again.")
        return 1

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
    print("\n  Stop the stack with: python scripts/aehub.py down")

    return 0


if __name__ == "__main__":
    sys.exit(main())
