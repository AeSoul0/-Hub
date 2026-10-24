"""
@file tests/desktop/test_release_manifest.py
@description M15: latest.json, the manifest installed apps poll for updates.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "desktop" / "scripts" / "release_manifest.py"
CONF = Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json"


def _module():
    spec = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_points_to_the_signed_installer(tmp_path):
    (tmp_path / "AEHub_1.0.0_x64-setup.exe").write_bytes(b"MZ")
    (tmp_path / "AEHub_1.0.0_x64-setup.exe.sig").write_text("c2lnbmF0dXJl\n", encoding="utf-8")

    manifest = _module().manifest("v1.0.0", tmp_path)

    assert manifest["version"] == "1.0.0"
    windows = manifest["platforms"]["windows-x86_64"]
    assert windows["signature"] == "c2lnbmF0dXJl"
    assert windows["url"] == "https://github.com/AeSoul0/-Hub/releases/download/v1.0.0/AEHub_1.0.0_x64-setup.exe"


def test_unsigned_installer_is_refused(tmp_path):
    (tmp_path / "AEHub_1.0.0_x64-setup.exe").write_bytes(b"MZ")

    with pytest.raises(SystemExit, match="signing key"):
        _module().manifest("v1.0.0", tmp_path)


def test_the_app_checks_updates_against_a_pinned_key():
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    updater = conf["plugins"]["updater"]

    assert updater["pubkey"].strip()
    assert updater["endpoints"] == ["https://github.com/AeSoul0/-Hub/releases/latest/download/latest.json"]
    # Never a plain-HTTP endpoint.
    assert all(endpoint.startswith("https://") for endpoint in updater["endpoints"])
