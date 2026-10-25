"""
@file tests/desktop/test_desktop_sidecar.py
@description M14 exit test (ADR-020): the desktop sidecar, end to end.

The real `backend/desktop.py`, as the Tauri shell starts it, from an empty
data folder:

1. it creates and starts its own Postgres + pgvector cluster and the API on
   free loopback ports, and announces the launch URL on stdout;
2. the launch token opens a session once; the static frontend is served from
   the same origin; foreign Host names and cross-origin writes are refused;
3. onboarding through the HTTP API: a provider key into the keyring
   (a file-backed fake here), models, prices, budget;
4. the first run proposes a HIGH-risk call, which waits for approval; once
   approved the run completes;
5. closing stdin stops the API and Postgres.

Only the model is fake: an OpenAI-compatible server in this process, used
through the "local" provider. Needs PostgreSQL with pgvector
(AEHUB_TEST_PG_BIN or initdb on PATH); skipped otherwise.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from types import SimpleNamespace
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pytest


BACKEND = Path(__file__).resolve().parents[2] / "backend"
WORKER = "desk-worker"
CRITIC = "desk-critic"
STARTUP_SECONDS = 180


def _pg_bin() -> Optional[Path]:
    sys.path.insert(0, str(BACKEND))
    from app.desktop.postgres import PostgresError, find_bin_dir

    try:
        return find_bin_dir(os.getenv("AEHUB_TEST_PG_BIN"))
    except PostgresError:
        return None


def _has_pgvector(bin_dir: Path) -> bool:
    pg_config = bin_dir / ("pg_config.exe" if sys.platform == "win32" else "pg_config")
    candidates = [bin_dir.parent / "share" / "extension"]

    if pg_config.is_file():
        share = subprocess.run([str(pg_config), "--sharedir"], capture_output=True, text=True).stdout.strip()
        if share:
            candidates.append(Path(share) / "extension")

    return any((folder / "vector.control").is_file() for folder in candidates)


PG_BIN = _pg_bin()
AVAILABLE = PG_BIN is not None and _has_pgvector(PG_BIN)

# CI sets AEHUB_REQUIRE_DESKTOP_TEST=1: there a missing pgvector is a broken
# setup, not a reason to skip the exit test.
if not AVAILABLE and os.getenv("AEHUB_REQUIRE_DESKTOP_TEST") == "1":
    raise RuntimeError(f"PostgreSQL with pgvector is required here (found binaries: {PG_BIN}).")

pytestmark = pytest.mark.skipif(
    not AVAILABLE,
    reason="PostgreSQL with pgvector not found (set AEHUB_TEST_PG_BIN)",
)


# ==============================================================================
# FAKE MODEL AND KEYRING
# ==============================================================================


class FakeModelServer:
    """
    OpenAI-compatible Chat Completions. The Worker asks for a shell command
    until it sees the tool's result, then answers; the Critic accepts.
    """

    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(body)
                reply = json.dumps(owner.answer(body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def answer(self, body: Dict[str, Any]) -> Dict[str, Any]:
        message: Dict[str, Any] = {"role": "assistant", "content": None}

        if body["model"] == CRITIC:
            message["content"] = json.dumps({"decision": "ACCEPT", "issues": []})
        elif any(item.get("role") == "tool" for item in body["messages"]):
            message["content"] = "The command ran after your approval."
        else:
            message["tool_calls"] = [
                {
                    "id": "call_shell_1",
                    "type": "function",
                    "function": {
                        "name": "execute_shell_script",
                        "arguments": json.dumps({"command": "echo hello"}),
                    },
                }
            ]

        return {
            "id": f"chatcmpl-{len(self.requests)}",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }

    def __enter__(self) -> "FakeModelServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()


FAKE_LAUNCHER = '''
import json
from pathlib import Path

STORE = Path(__file__).with_name("keyring.json")
SECRETS = {
    "AEHUB_SECRET_KEY": "login key",
    "OPENAI_API_KEY": "OpenAI",
    "OPENROUTER_API_KEY": "OpenRouter",
    "GROQ_API_KEY": "Groq",
}


class FileStore:
    name = "test file store"

    def _load(self):
        return json.loads(STORE.read_text()) if STORE.exists() else {}

    def get(self, key):
        return self._load().get(key)

    def set(self, key, value):
        values = self._load()
        values[key] = value
        STORE.write_text(json.dumps(values))


def open_store():
    return FileStore()


def ensure_login_key(store):
    if not store.get("AEHUB_SECRET_KEY"):
        store.set("AEHUB_SECRET_KEY", "desktop-test-login-key")
'''


# ==============================================================================
# SIDECAR PROCESS
# ==============================================================================


def _sidecar_env(tmp_path: Path, model_url: str) -> Dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AEHUB_", "OPENAI_", "OPENROUTER_", "GROQ_", "POSTGRES_", "REDIS_"))
    }
    env.update(
        {
            "AEHUB_LAUNCHER": str(tmp_path / "launcher" / "aehub_launcher.py"),
            "AEHUB_LOCAL_BASE_URL": model_url,
            "AEHUB_ALLOWED_DIRS": str(tmp_path / "workspace"),
            "AEHUB_EMBEDDER": "hash",
            # No speech model downloads in a test run.
            "AEHUB_VOICE": "off",
            "AEHUB_TELEMETRY_CONSOLE": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _read_line(stream, timeout: float) -> Dict[str, Any]:
    lines: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()

    try:
        line = lines.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError("The sidecar did not announce itself in time.") from None

    assert line, "The sidecar exited before announcing itself."
    return json.loads(line)


def _wait(predicate, timeout: float, what: str):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)

    raise AssertionError(f"Timed out waiting for {what}.")


@contextmanager
def running_sidecar(tmp_path: Path, frontend: Path):
    """
    The real sidecar from an empty data folder, the fake model behind it.
    On exit stdin is closed, as the window does; `app.process` is then done.
    """
    (tmp_path / "launcher").mkdir()
    (tmp_path / "launcher" / "aehub_launcher.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    data_dir = tmp_path / "data"
    stderr_log = tmp_path / "sidecar.log"

    with FakeModelServer() as model, open(stderr_log, "w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [
                sys.executable,
                str(BACKEND / "desktop.py"),
                "--data-dir", str(data_dir),
                "--pg-bin", str(PG_BIN),
                "--frontend-dir", str(frontend),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            env=_sidecar_env(tmp_path, model.base_url),
        )
        app = SimpleNamespace(process=process, model=model, log=stderr_log, data_dir=data_dir)

        try:
            ready = _read_line(process.stdout, STARTUP_SECONDS)
            assert ready["event"] == "ready", (ready, stderr_log.read_text(encoding="utf-8")[-4000:])
            app.ready = ready
            app.launch_url = ready["url"]
            app.origin = f"http://127.0.0.1:{ready['port']}"
            yield app
        finally:
            # Closing stdin stops everything.
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                raise


def configure_models(put, post) -> None:
    """
    Onboarding as the setup page sends it: local models, prices, budget.
    """
    roles = {role: [f"local:{WORKER}"] for role in ("architect", "research", "fast_worker", "triage")}
    roles["critic"] = [f"local:{CRITIC}"]
    configured = put(
        "/api/settings",
        {
            "values": {
                "AEHUB_MODEL_ROLES": json.dumps(roles),
                "AEHUB_MODEL_PRICES": json.dumps(
                    {WORKER: {"input": 1.0, "output": 2.0}, CRITIC: {"input": 0.5, "output": 1.0}}
                ),
                "AEHUB_MONTHLY_BUDGET": "5",
                "AEHUB_RUN_MAX_COST": "1",
            }
        },
    )
    assert configured["ready"] is True, configured["issues"]
    assert post("/api/settings/onboarding")["onboarding"]["completed"] is True


def _postgres_stopped(data_dir: Path) -> bool:
    status = subprocess.run(
        [str(PG_BIN / ("pg_ctl.exe" if sys.platform == "win32" else "pg_ctl")), "status", "-D", str(data_dir / "pgdata")],
        capture_output=True,
        text=True,
    )
    return status.returncode != 0


def _finished(client: httpx.Client, run_id: str):
    detail = client.get(f"/api/runs/{run_id}").json()
    return detail if detail["status"] in ("completed", "failed") else None


def test_install_to_first_approved_run(tmp_path):
    frontend = tmp_path / "out"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><title>ÆHub</title><p>desktop</p>", encoding="utf-8")

    with running_sidecar(tmp_path, frontend) as app:
        origin, launch_url, model = app.origin, app.launch_url, app.model
        assert app.ready["frontend"] is True
        assert launch_url.startswith(f"{origin}/desktop/launch/")

        # The database password was generated into the keyring.
        keyring = json.loads((tmp_path / "launcher" / "keyring.json").read_text())
        assert len(keyring["AEHUB_DESKTOP_DB_PASSWORD"]) >= 32

        # --- 2. launch token, same origin, loopback hardening ----------
        with httpx.Client(base_url=origin, timeout=60) as anonymous:
            assert anonymous.get("/api/settings").status_code == 401
            assert anonymous.get("/health", headers={"Host": "evil.example"}).status_code == 400

        client = httpx.Client(base_url=origin, timeout=120)
        opened = client.get(launch_url, follow_redirects=False)
        assert opened.status_code == 303
        assert "aehub_session_token" in client.cookies

        with httpx.Client(base_url=origin, timeout=60) as stranger:
            assert stranger.get(launch_url, follow_redirects=False).status_code == 403

        page = client.get("/")
        assert page.status_code == 200 and "desktop" in page.text
        assert "'unsafe-inline'" in page.headers["content-security-policy"]

        assert client.get("/api/desktop").json() == {"desktop": True, "keyring": True}
        foreign = client.put(
            "/api/desktop/secrets",
            json={"OPENROUTER_API_KEY": "sk-or-x"},
            headers={"Origin": "http://localhost:9999"},
        )
        assert foreign.status_code == 403

        # --- 3. onboarding ----------------------------------------------
        saved = client.put(
            "/api/desktop/secrets",
            json={"OPENROUTER_API_KEY": "sk-or-desktop-test"},
            headers={"Origin": origin},
        )
        assert saved.status_code == 200, saved.text
        keyring = json.loads((tmp_path / "launcher" / "keyring.json").read_text())
        assert keyring["OPENROUTER_API_KEY"] == "sk-or-desktop-test"

        configure_models(
            lambda path, body: client.put(path, json=body).json(),
            lambda path: client.post(path).json(),
        )

        # --- 4. first run: HIGH call waits for the owner -----------------
        asked = client.post(
            "/api/orchestrator/ask",
            data={"text": "Run echo hello in the sandbox shell."},
        )
        assert asked.status_code == 200, asked.text

        pending = _wait(lambda: client.get("/api/approvals").json(), 60, "the approval request")
        assert len(pending) == 1
        approval = pending[0]
        assert approval["tool"] == "execute_shell_script"
        run_id = approval["run_id"]
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "waiting_approval"

        decided = client.post(f"/api/approvals/{approval['id']}", json={"decision": "allow"})
        assert decided.status_code == 200, decided.text

        run = _wait(lambda: _finished(client, run_id), 120, "the run to finish")
        assert run["status"] == "completed", run
        assert {request["model"] for request in model.requests} == {WORKER, CRITIC}
        client.close()

    # --- 5. closing stdin stops everything -------------------------------
    assert app.process.returncode == 0, app.log.read_text(encoding="utf-8")[-4000:]
    assert _postgres_stopped(app.data_dir), "Postgres is still running after the sidecar stopped."


# ==============================================================================
# BROWSER SMOKE (M11 leftover, done in M15)
# ==============================================================================


EXPORT = BACKEND.parent / "frontend" / "out"


@pytest.mark.skipif(
    os.getenv("AEHUB_BROWSER_SMOKE") != "1" or not (EXPORT / "index.html").is_file(),
    reason="browser smoke: AEHUB_BROWSER_SMOKE=1, the static export and Playwright's Chromium",
)
def test_browser_smoke(tmp_path):
    """
    What a person does on first start, in a real Chromium: the launch URL
    logs in, a command typed in the Nucleo starts a run, its events show up
    live, the HIGH call is allowed from the Nucleo, the run shows as
    completed. No page script is blocked by the CSP.
    """
    from playwright.sync_api import expect, sync_playwright

    with running_sidecar(tmp_path, EXPORT) as app, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        console_errors: List[str] = []
        page.on("console", lambda message: message.type == "error" and console_errors.append(message.text))

        try:
            # 1. The launch URL opens the Control Plane, logged in.
            page.goto(app.launch_url)
            page.wait_for_url(f"{app.origin}/control-plane**")
            expect(page.get_by_text("APPROVAZIONI").first).to_be_visible()

            # 2. Models and budget, as the setup page saves them.
            configure_models(
                lambda path, body: context.request.put(f"{app.origin}{path}", data=body).json(),
                lambda path: context.request.post(f"{app.origin}{path}").json(),
            )

            # 3. A typed command in the Nucleo, the home page (F1), once its
            # live stream is open.
            page.goto(f"{app.origin}/")
            expect(page.get_by_text("in linea")).to_be_visible(timeout=30_000)
            command = page.get_by_role("textbox", name="Comando")
            command.fill("Run echo hello in the sandbox shell.")
            # The run parks on the approval before the request returns.
            with page.expect_response("**/api/orchestrator/ask", timeout=120_000) as asked:
                command.press("Enter")
            assert asked.value.ok, asked.value.text()

            # 4. The engine's events arrive live; the HIGH call waits in the
            # Nucleo and the owner allows it there.
            expect(page.get_by_text("tool.approval_required").first).to_be_visible(timeout=60_000)
            allow = page.get_by_role("button", name="Consenti")
            expect(allow).to_be_visible(timeout=60_000)
            expect(page.get_by_text("execute_shell_script").first).to_be_visible()
            allow.click()
            expect(allow).to_be_hidden(timeout=60_000)

            # 5. The run completes.
            page.goto(f"{app.origin}/control-plane/runs/")
            expect(page.get_by_role("cell", name="completata").first).to_be_visible(timeout=120_000)

            blocked = [text for text in console_errors if "Content Security Policy" in text]
            assert blocked == [], blocked
        finally:
            context.close()
            browser.close()

    assert app.process.returncode == 0, app.log.read_text(encoding="utf-8")[-4000:]
