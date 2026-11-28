"""
@file tests/unit/test_windows_launcher.py
@description N11: ÆHub starts on Windows with a double click.

AEHub.cmd runs start.ps1 with Windows PowerShell; start.ps1 starts Docker
Desktop when it is not running, runs the launcher's setup on the first run,
starts the stack, waits until it answers, opens the browser and puts an icon
on the desktop once. CI parses it in Windows PowerShell 5.1 and PowerShell 7
(job windows-launcher); this test checks what can be checked anywhere.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_double_click_wrapper_runs_start_ps1():
    raw = (ROOT / "AEHub.cmd").read_bytes()
    # cmd.exe reads a batch file in the OEM code page: ASCII only, CRLF lines.
    assert raw.isascii()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("ascii")
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*' in text
    # A failure stays on screen instead of closing the window.
    assert "pause" in text


def test_start_ps1_does_every_step():
    raw = (ROOT / "start.ps1").read_bytes()
    # Windows PowerShell 5.1 reads a file without BOM as ANSI: the accents need it.
    assert raw.startswith(b"\xef\xbb\xbf")
    script = raw.decode("utf-8-sig")
    for step in (
        "Docker Desktop.exe",  # starts Docker Desktop when it is not running
        "scripts/aehub.py login-key",  # first run?
        "scripts/aehub.py setup",
        "scripts/aehub.py up",
        "scripts/aehub.py down",  # -Stop
        "http://localhost:3002/health",  # waits until it answers
        "Start-Process ($(if ($firstRun) { $SetupUrl } else { $NucleoUrl }))",
        "WScript.Shell",  # the desktop icon
        "AEHub.cmd",
    ):
        assert step in script, step
    # Keys go to the Credential Manager through the launcher, never to a file.
    assert "Set-Content" not in script and "Out-File" not in script
    # Not "Stop": 5.1 would end the script on a native command's error output.
    assert '$ErrorActionPreference = "Stop"' not in script


def test_the_suspended_desktop_app_is_not_part_of_it():
    """It only borrows the app's icon for the shortcut; it never builds or starts the app."""
    script = (ROOT / "start.ps1").read_text(encoding="utf-8-sig").lower()
    for command in ("cargo ", "tauri build", "tauri dev", "npm run tauri", "desktop.py"):
        assert command not in script, command
