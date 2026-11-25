"""
@file backend/app/instant/apps.py
@description The apps and folders the user lets ÆHub open, and how they are opened (V1, ADR-035).

AEHUB_APPS is a JSON object chosen by the owner in Settings: a name the user
says ("spotify") -> what to start, either a path or command ("C:/.../Spotify.exe",
"firefox") or a list of program and arguments (["code", "--new-window"]).
Nothing else can be started: there is no shell and no free command line.

Programs start detached, with no console window: on Windows DETACHED_PROCESS,
elsewhere a new session with the output thrown away. A link, a document or a
URI scheme ("spotify:") is handed to the system's opener.

Opening an app works only when the backend runs on the user's computer (the
desktop app or a local backend). Inside a container it would start the
program in the container, so the tools are not offered there.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from app.core.runtime_config import config_value

APPS_SETTING = "AEHUB_APPS"
NAME = re.compile(r"^[^\W_][\w .'+-]{0,39}$")
MAX_APPS = 50

# Folders that can be opened by name, in Italian and in English.
FOLDERS: Dict[str, str] = {
    "download": "Downloads",
    "downloads": "Downloads",
    "scaricati": "Downloads",
    "documenti": "Documents",
    "documents": "Documents",
    "scrivania": "Desktop",
    "desktop": "Desktop",
    "immagini": "Pictures",
    "foto": "Pictures",
    "pictures": "Pictures",
    "photos": "Pictures",
    "musica": "Music",
    "music": "Music",
    "video": "Videos",
    "videos": "Videos",
}


class AppConfigError(ValueError):
    """AEHUB_APPS is not a valid list of apps."""


class LaunchError(RuntimeError):
    """The app or folder could not be opened."""


def parse_apps(raw: str) -> Dict[str, List[str]]:
    """
    Read AEHUB_APPS: name -> program and arguments. Names are matched without
    case. Raises AppConfigError with a message for the Settings page.
    """
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppConfigError(f"The app list is not valid JSON: {exc.msg}.") from exc
    if not isinstance(data, dict):
        raise AppConfigError('The app list must be a JSON object, e.g. {"spotify": "spotify"}.')
    if len(data) > MAX_APPS:
        raise AppConfigError(f"At most {MAX_APPS} apps.")

    apps: Dict[str, List[str]] = {}
    for name, target in data.items():
        key = str(name).strip().lower()
        if not NAME.fullmatch(key):
            raise AppConfigError(f"'{name}' is not a valid app name (letters, digits, spaces; at most 40).")
        if isinstance(target, str):
            command = [target.strip()]
        elif isinstance(target, list) and target and all(isinstance(part, str) for part in target):
            command = [part for part in target]
        else:
            raise AppConfigError(f"'{name}': give a path or command, or a list of program and arguments.")
        if not command[0].strip():
            raise AppConfigError(f"'{name}': the program is empty.")
        if key in apps:
            raise AppConfigError(f"'{name}' is listed twice.")
        apps[key] = command
    return apps


def configured_apps() -> Dict[str, List[str]]:
    """The apps in the current settings; an invalid list counts as none."""
    try:
        return parse_apps(config_value(APPS_SETTING) or "")
    except AppConfigError:
        return {}


def in_container() -> bool:
    """Whether the backend runs inside a container, where host apps are out of reach."""
    if os.environ.get("AEHUB_IN_CONTAINER") == "1":
        return True
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _opener() -> Optional[List[str]]:
    """The command that opens a link, a document or a folder with its default app."""
    if sys.platform == "darwin":
        return ["open"]
    opener = shutil.which("xdg-open")
    return [opener] if opener else None


def _detached(command: List[str]) -> None:
    """Start a program and return at once, with no console window and no output kept."""
    options: Dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    # A list and no shell: the configured program runs with exactly its
    # arguments, nothing the user says is interpreted.
    subprocess.Popen(command, **options)  # noqa: S603 - program from the owner's own app list


def _is_document_or_uri(target: str) -> bool:
    if re.match(r"^[a-z][a-z0-9+.-]*:(?![\\/])", target, re.IGNORECASE):
        return True  # "spotify:", "ms-settings:", "https://..."; not "C:\\..."
    return Path(target).suffix.lower() in {".lnk", ".url", ".desktop", ".app"}


def launch(command: List[str]) -> None:
    """Open one configured app. Raises LaunchError when it cannot start."""
    if in_container():
        raise LaunchError("ÆHub runs in a container here: it can open apps only when it runs on your computer.")
    program = command[0]
    try:
        if len(command) == 1 and _is_document_or_uri(program):
            if sys.platform == "win32":
                os.startfile(program)  # type: ignore[attr-defined]  # noqa: S606 - owner's own app list
                return
            opener = _opener()
            if opener is None:
                raise LaunchError("No program here opens links or documents.")
            _detached(opener + [program])
            return
        if shutil.which(program) is None and not Path(program).exists():
            raise LaunchError(f"'{program}' was not found on this computer.")
        _detached(command)
    except OSError as exc:
        raise LaunchError(f"'{program}' could not start: {exc.strerror or exc}.") from exc


def folder_path(name: str) -> Path:
    """The folder a spoken name stands for, in the user's home."""
    key = FOLDERS.get(name.strip().lower())
    if key is None:
        raise LaunchError(f"'{name}' is not a folder ÆHub knows.")
    return Path.home() / key


def open_folder(name: str) -> Path:
    """Open a known folder in the file manager. Raises LaunchError."""
    if in_container():
        raise LaunchError("ÆHub runs in a container here: it can open folders only when it runs on your computer.")
    path = folder_path(name)
    if not path.is_dir():
        raise LaunchError(f"The folder {path} does not exist.")
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 - a fixed folder in the user's home
            return path
        opener = _opener()
        if opener is None:
            raise LaunchError("No file manager is available here.")
        _detached(opener + [str(path)])
    except OSError as exc:
        raise LaunchError(f"The folder could not be opened: {exc.strerror or exc}.") from exc
    return path


__all__ = [
    "APPS_SETTING",
    "AppConfigError",
    "FOLDERS",
    "LaunchError",
    "configured_apps",
    "folder_path",
    "in_container",
    "launch",
    "open_folder",
    "parse_apps",
]
