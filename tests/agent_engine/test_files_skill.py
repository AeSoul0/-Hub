"""
@file tests/agent_engine/test_files_skill.py
@description F11 (ADR-036): the agents use the user's files, only in the folders the owner chose.

- the folders: the working folder plus AEHUB_AGENT_FOLDERS, validated as a
  setting; anything outside is refused;
- inside an allowed folder ÆHub's own code and data, the device file,
  hidden files and AppData stay out of reach;
- each tool: list, find, read, write (never replaces), make a folder, move
  (never replaces), replace and delete;
- through the Tool Gateway: a path outside is refused before the tool runs,
  replacing and deleting wait for the owner's approval, reading marks the
  output untrusted.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agent_engine import guardrails
from app.agent_engine.errors import ApprovalRequiredError
from app.agent_engine.guardrails import GuardrailException, allowed_directories, validate_path
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum
from app.core.settings_service import SettingsValidationError, validate_changes
from app.skills import files_skill
from app.skills.files_skill import FilesSkill


OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-f11")


@pytest.fixture
def folders(tmp_path, monkeypatch):
    """A working folder and one folder the owner chose, with a few files."""
    work = tmp_path / "work"
    work.mkdir()
    mine = tmp_path / "Documents"
    (mine / "Progetti").mkdir(parents=True)
    (mine / "Progetti" / "piano.md").write_text("# Piano\nPrima riga.", encoding="utf-8")
    (mine / "report.pdf").write_bytes(b"%PDF\x00\x01binary")
    (mine / ".ssh").mkdir()
    (mine / ".ssh" / "id_ed25519").write_text("secret", encoding="utf-8")
    (mine / ".env").write_text("KEY=secret", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("no", encoding="utf-8")

    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(work))
    replace_stored({"AEHUB_AGENT_FOLDERS": json.dumps([str(mine)])})
    yield type("Folders", (), {"work": work, "mine": mine, "root": tmp_path})
    replace_stored({})


def run(coroutine):
    return asyncio.run(coroutine)


# ==============================================================================
# WHERE THE AGENTS MAY GO
# ==============================================================================


def test_the_chosen_folders_join_the_working_folder(folders):
    assert allowed_directories() == [folders.work.resolve(), folders.mine.resolve()]
    assert validate_path(str(folders.mine / "Progetti" / "piano.md")) == (folders.mine / "Progetti" / "piano.md").resolve()
    # A relative path is inside the working folder.
    assert validate_path("notes.txt") == (folders.work / "notes.txt").resolve()

    for outside in (str(folders.root / "outside.txt"), str(folders.mine / ".." / "outside.txt"), "/etc/passwd"):
        with pytest.raises(GuardrailException, match="outside"):
            validate_path(outside)


def test_hidden_files_and_aehub_itself_stay_out_of_reach(folders, monkeypatch):
    for hidden in (folders.mine / ".ssh" / "id_ed25519", folders.mine / ".env", folders.mine / "AppData" / "x"):
        with pytest.raises(GuardrailException, match="hidden"):
            validate_path(str(hidden))

    # Even a folder chosen around ÆHub's code does not reach it.
    replace_stored({"AEHUB_AGENT_FOLDERS": json.dumps([str(guardrails._BACKEND_DIR.parent)])})
    with pytest.raises(GuardrailException, match="ÆHub itself"):
        validate_path(str(guardrails._BACKEND_DIR / "main.py"))

    # The home device file, wherever it is.
    device_file = folders.mine / "home.json"
    device_file.write_text("{}", encoding="utf-8")
    replace_stored({"AEHUB_AGENT_FOLDERS": json.dumps([str(folders.mine)])})
    monkeypatch.setenv("AEHUB_HOME_DEVICES", str(device_file))
    with pytest.raises(GuardrailException, match="ÆHub itself"):
        validate_path(str(device_file))


def test_the_folder_list_is_validated(tmp_path):
    validate_changes({"AEHUB_AGENT_FOLDERS": json.dumps([str(tmp_path)])})
    validate_changes({"AEHUB_AGENT_FOLDERS": ""})

    for bad in ("not json", '"one"', "[1]", '["relative/path"]', json.dumps([str(tmp_path / "missing")])):
        with pytest.raises(SettingsValidationError) as refused:
            validate_changes({"AEHUB_AGENT_FOLDERS": bad})
        assert "AEHUB_AGENT_FOLDERS" in refused.value.errors


# ==============================================================================
# THE TOOLS
# ==============================================================================


def test_list_find_and_read(folders):
    listing = run(files_skill.list_folder(str(folders.mine)))
    assert "[folder] Progetti/" in listing and "report.pdf" in listing
    assert ".ssh" not in listing and ".env" not in listing

    found = run(files_skill.find_files("piano"))
    assert str(folders.mine / "Progetti" / "piano.md") in found
    assert "id_ed25519" not in run(files_skill.find_files("*"))

    assert run(files_skill.read_file(str(folders.mine / "Progetti" / "piano.md"))) == "# Piano\nPrima riga."
    assert "binary" in run(files_skill.read_file(str(folders.mine / "report.pdf")))


def test_write_make_and_move_never_replace(folders):
    target = folders.mine / "Progetti" / "nuovo.txt"
    assert run(files_skill.write_file(str(target), "ciao")).startswith("Wrote")
    assert target.read_text(encoding="utf-8") == "ciao"

    assert "already exists" in run(files_skill.write_file(str(target), "altro"))
    assert target.read_text(encoding="utf-8") == "ciao"

    assert run(files_skill.make_folder(str(folders.mine / "Archivio"))).startswith("Created")
    moved = run(files_skill.move_path(str(target), str(folders.mine / "Archivio")))
    assert moved.startswith("Moved") and (folders.mine / "Archivio" / "nuovo.txt").exists()

    (folders.mine / "altro.txt").write_text("x", encoding="utf-8")
    assert "already exists" in run(files_skill.move_path(str(folders.mine / "altro.txt"), str(folders.mine / "Archivio" / "nuovo.txt")))


def test_replace_and_delete(folders):
    file = folders.mine / "Progetti" / "piano.md"
    assert run(files_skill.replace_file(str(file), "nuovo")).startswith("Replaced")
    assert file.read_text(encoding="utf-8") == "nuovo"

    assert "not empty" in run(files_skill.delete_path(str(folders.mine / "Progetti")))
    assert run(files_skill.delete_path(str(file))).startswith("Deleted")
    assert run(files_skill.delete_path(str(folders.mine / "Progetti"))).startswith("Deleted the empty folder")
    assert "cannot be deleted" in run(files_skill.delete_path(str(folders.mine)))


def test_the_tools_check_paths_themselves(folders):
    with pytest.raises(GuardrailException):
        run(files_skill.read_file(str(folders.root / "outside.txt")))
    with pytest.raises(GuardrailException):
        run(files_skill.write_file(str(folders.mine / ".env"), "KEY=other"))
    assert (folders.mine / ".env").read_text(encoding="utf-8") == "KEY=secret"


def test_risks_and_flags():
    tools = FilesSkill().get_tool_metadata()

    assert {name: meta.risk_level.value for name, meta in tools.items()} == {
        "list_folder": "low",
        "find_files": "low",
        "read_file": "low",
        "write_file": "medium",
        "make_folder": "low",
        "move_path": "medium",
        "replace_file": "high",
        "delete_path": "high",
    }
    assert all(meta.filesystem_access for meta in tools.values())
    assert tools["replace_file"].requires_approval and tools["delete_path"].requires_approval
    assert tools["read_file"].untrusted_output and tools["list_folder"].untrusted_output


# ==============================================================================
# THROUGH THE TOOL GATEWAY
# ==============================================================================


@pytest.fixture
def gateway(agent_infrastructure, folders, monkeypatch):
    registry = agent_infrastructure.use_skills(FilesSkill())
    monkeypatch.setattr("app.skills.registry.skill_registry", registry)
    return folders


def _call(tool: str, arguments: dict):
    from app.runtime.direct_tool import run_tool

    return run(run_tool(OWNER, tool, arguments, session_id="s-f11", run_id=f"run-{tool}", call_id=f"call-{tool}"))


def test_the_gateway_refuses_a_path_outside_before_the_tool_runs(gateway):
    result = _call("read_file", {"path": str(gateway.root / "outside.txt")})
    assert result.success is False and "outside" in (result.error or "")

    written = _call("write_file", {"path": str(gateway.mine / "via-gateway.txt"), "content": "ok"})
    assert written.success is True and (gateway.mine / "via-gateway.txt").read_text(encoding="utf-8") == "ok"


def test_replacing_or_deleting_waits_for_the_owner(gateway):
    for tool, arguments in (
        ("replace_file", {"path": str(gateway.mine / "Progetti" / "piano.md"), "content": "x"}),
        ("delete_path", {"path": str(gateway.mine / "Progetti" / "piano.md")}),
    ):
        with pytest.raises(ApprovalRequiredError):
            _call(tool, arguments)

    assert (gateway.mine / "Progetti" / "piano.md").read_text(encoding="utf-8") == "# Piano\nPrima riga."
