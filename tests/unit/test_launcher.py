"""
@file tests/unit/test_launcher.py
@description M12: the launcher keeps secrets in the OS keyring, moves them
out of backend/.env, and hands them to Docker Compose only through the
process environment.

The keyring is an in-memory fake; the Windows Credential Manager backend was
checked by hand against the real store and the `keyring` package.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_launcher():
    spec = importlib.util.spec_from_file_location("aehub_launcher", ROOT / "scripts" / "aehub.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["aehub_launcher"] = module
    spec.loader.exec_module(module)
    return module


aehub = load_launcher()


class MemoryStore:
    name = "memory"

    def __init__(self, values: Optional[Dict[str, str]] = None) -> None:
        self.values = dict(values or {})

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def scripted(answers: List[str]):
    """
    An `ask` that replays answers and records the questions.
    """
    asked: List[str] = []

    def ask(question: str, secret: bool) -> str:
        asked.append(question)
        return answers.pop(0) if answers else ""

    ask.asked = asked
    return ask


def test_migration_moves_keys_out_of_the_env_file(tmp_path):
    env = tmp_path / "backend.env"
    env.write_text(
        "# Created by make demo.\n"
        "AEHUB_SECRET_KEY=login-key-from-file\n"
        "GROQ_API_KEY=not-configured\n"
        "OPENAI_API_KEY=sk-from-file\n"
        "OPENAI_MODEL=gpt-test\n",
        encoding="utf-8",
    )
    store = MemoryStore()

    moved = aehub.migrate_env_secrets(store, env)

    assert sorted(moved) == ["AEHUB_SECRET_KEY", "OPENAI_API_KEY"]
    assert store.values == {
        "AEHUB_SECRET_KEY": "login-key-from-file",
        "OPENAI_API_KEY": "sk-from-file",
    }
    # Placeholders are dropped, settings and comments stay.
    assert env.read_text(encoding="utf-8") == "# Created by make demo.\nOPENAI_MODEL=gpt-test\n"


def test_migration_never_overwrites_the_keyring(tmp_path, capsys):
    env = tmp_path / "backend.env"
    env.write_text("OPENAI_API_KEY=sk-old\nOPENROUTER_API_KEY=or-same\n", encoding="utf-8")
    store = MemoryStore({"OPENAI_API_KEY": "sk-new", "OPENROUTER_API_KEY": "or-same"})

    assert aehub.migrate_env_secrets(store, env) == []
    assert store.values["OPENAI_API_KEY"] == "sk-new"

    # A different key stays in the file, with a warning that names it only.
    assert env.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-old\n"
    output = capsys.readouterr().out
    assert "OPENAI_API_KEY" in output
    assert "sk-old" not in output and "sk-new" not in output


def test_setup_on_a_clean_machine(tmp_path, capsys):
    root_env = tmp_path / ".env"
    backend_env = tmp_path / "backend" / ".env"
    store = MemoryStore()
    # Model key, MQTT password (skipped), ElevenLabs key (skipped), folder.
    ask = scripted(["sk-typed", "", "", "my-files"])

    aehub.setup(store, ask=ask, root_env=root_env, backend_env=backend_env, root=tmp_path)

    assert store.get("OPENAI_API_KEY") == "sk-typed"
    assert store.get("ELEVENLABS_API_KEY") is None
    assert store.get("GROQ_API_KEY") is None
    assert len(store.get("AEHUB_SECRET_KEY")) >= 32

    root_values = aehub.read_env(root_env)
    assert root_values["AEHUB_WORKSPACE_DIR"] == "my-files"
    assert len(root_values["POSTGRES_PASSWORD"]) >= 24
    assert (tmp_path / "my-files").is_dir()

    # Nothing secret reaches a file or the terminal.
    assert not backend_env.exists()
    output = capsys.readouterr().out
    for secret in store.values.values():
        assert secret not in output
        assert secret not in root_env.read_text(encoding="utf-8")

    # A second run asks nothing it already has and keeps the login key.
    login_key = store.get("AEHUB_SECRET_KEY")
    # Optional keys still unset are offered again: MQTT, ElevenLabs, folder.
    again = scripted(["", "", "other-files"])
    aehub.setup(store, ask=again, root_env=root_env, backend_env=backend_env, root=tmp_path)

    assert store.get("AEHUB_SECRET_KEY") == login_key
    assert not any("OPENAI_API_KEY" in question for question in again.asked)
    assert aehub.read_env(root_env)["AEHUB_WORKSPACE_DIR"] == "other-files"
    assert root_env.read_text(encoding="utf-8").count("AEHUB_WORKSPACE_DIR=") == 1


def test_up_passes_keys_to_compose_through_the_environment(monkeypatch, tmp_path):
    store = MemoryStore({"AEHUB_SECRET_KEY": "login", "OPENAI_API_KEY": "sk-run"})
    calls = []

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(aehub, "BACKEND_ENV", tmp_path / "missing.env")
    monkeypatch.setattr(aehub.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        aehub.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    aehub.up(store, build=False, services=["backend"])

    [(command, kwargs)] = calls
    assert command == ["docker", "compose", "up", "-d", "backend"]
    assert kwargs["env"]["OPENAI_API_KEY"] == "sk-run"
    assert kwargs["env"]["AEHUB_SECRET_KEY"] == "login"
    assert "GROQ_API_KEY" not in kwargs["env"]
    assert kwargs["check"] is True


def test_up_needs_a_login_key():
    with pytest.raises(aehub.LauncherError, match="setup"):
        aehub.up(MemoryStore())


def test_secrets_report_never_shows_values():
    store = MemoryStore({"OPENAI_API_KEY": "sk-visible?"})
    report = "\n".join(aehub.secrets_report(store))

    assert "sk-visible?" not in report
    assert "OPENAI_API_KEY" in report and "set" in report
    assert "AEHUB_MQTT_PASSWORD" in report and "not set" in report
    assert "GROQ_API_KEY" not in report


def test_no_keyring_explains_how_to_get_one(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    monkeypatch.setattr(aehub.sys, "platform", "linux")

    with pytest.raises(aehub.LauncherError, match="pip install keyring"):
        aehub.open_store()


def test_compose_secrets_match_the_launcher():
    """
    Every key the launcher manages reaches the backend container, and only
    through interpolation (never a literal value in the file).
    """
    compose = (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")

    for key in aehub.SECRETS:
        assert f"- {key}=${{{key}:-}}" in compose


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "aehub.py"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "setup" in result.stdout and "login-key" in result.stdout
