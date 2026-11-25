"""
@file desktop/scripts/smoke_sidecar.py
@description Start the engine from the assembled bundle, as the installed app
does, and check it answers (M14). Run after bundle.py:

    python desktop/scripts/smoke_sidecar.py

From an empty data folder: the bundled Python runs desktop.py, which creates
the bundled Postgres cluster (pgvector included), serves the frontend and
announces a launch URL. The launch token must open the app once; closing
stdin must stop everything with exit code 0.

Secrets go to a throwaway file, never to this machine's keyring. Only the
standard library is used.
"""

from __future__ import annotations

import http.client
import json
import os
import queue
import subprocess  # nosec B404 - runs the bundled interpreter only
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit


RESOURCES = Path(__file__).resolve().parents[1] / "src-tauri" / "resources"
STARTUP_SECONDS = 240

FAKE_LAUNCHER = '''
import json
from pathlib import Path

STORE = Path(__file__).with_name("keyring.json")
SECRETS = {"AEHUB_SECRET_KEY": "login key"}


class FileStore:
    name = "smoke test file store"

    def get(self, key):
        return json.loads(STORE.read_text()).get(key) if STORE.exists() else None

    def set(self, key, value):
        values = json.loads(STORE.read_text()) if STORE.exists() else {}
        values[key] = value
        STORE.write_text(json.dumps(values))


def open_store():
    return FileStore()


def ensure_login_key(store):
    if not store.get("AEHUB_SECRET_KEY"):
        store.set("AEHUB_SECRET_KEY", "smoke-login-key")
'''


def request(origin: str, path: str):
    parts = urlsplit(origin)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=60)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read().decode("utf-8", errors="replace")
    connection.close()
    return response.status, dict(response.getheaders()), body


def main() -> int:
    python = RESOURCES / "python" / ("python.exe" if sys.platform == "win32" else "bin/python3")

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        launcher = temp_dir / "aehub_launcher.py"
        launcher.write_text(FAKE_LAUNCHER, encoding="utf-8")
        log = temp_dir / "engine.log"

        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("AEHUB_", "POSTGRES_", "REDIS_"))
        }
        env.update(
            {
                "AEHUB_LAUNCHER": str(launcher),
                "AEHUB_ALLOWED_DIRS": str(temp_dir / "workspace"),
            }
        )

        with open(log, "w", encoding="utf-8") as stderr:
            engine = subprocess.Popen(  # nosec B603
                [
                    str(python), "-I", str(RESOURCES / "backend" / "desktop.py"),
                    "--data-dir", str(temp_dir / "data"),
                    "--pg-bin", str(RESOURCES / "postgres" / "bin"),
                    "--frontend-dir", str(RESOURCES / "frontend"),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                env=env,
            )

            try:
                lines: "queue.Queue[str]" = queue.Queue()
                threading.Thread(target=lambda: lines.put(engine.stdout.readline()), daemon=True).start()
                ready = json.loads(lines.get(timeout=STARTUP_SECONDS) or "{}")

                if ready.get("event") != "ready":
                    raise SystemExit(f"engine did not start: {ready}\n{log.read_text(encoding='utf-8')[-4000:]}")

                origin = f"http://127.0.0.1:{ready['port']}"
                launch_path = urlsplit(ready["url"]).path

                checks = [
                    ("health", request(origin, "/health")[0] == 200),
                    ("frontend", "<html" in request(origin, "/")[2].lower()),
                    ("launch token", request(origin, launch_path)[0] == 303),
                    ("token single use", request(origin, launch_path)[0] == 403),
                ]

                for name, passed in checks:
                    print(f"{'ok' if passed else 'FAILED':6} {name}")

                if not all(passed for _, passed in checks):
                    raise SystemExit(1)
            finally:
                engine.stdin.close()
                code = engine.wait(timeout=90)

        print(f"engine exit code {code}")
        if code != 0:
            print(log.read_text(encoding="utf-8")[-4000:])

        return code


if __name__ == "__main__":
    sys.exit(main())
