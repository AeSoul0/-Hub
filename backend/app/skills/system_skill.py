"""
@file backend/app/skills/system_skill.py
@description The computer's own controls, and timers and reminders (N4).

    media_control    LOW      volume up/down, mute, play/pause, next, previous
    lock_screen      LOW      lock the computer
    take_screenshot  MEDIUM   a screenshot, saved in the working folder
    set_timer        LOW      ring in N minutes
    set_reminder     LOW      "ricordami tra 10 minuti / alle 18 di ..."
    list_reminders   LOW      the timers and reminders waiting

The first three act on the computer ÆHub runs on, so inside a container
(Docker, a codespace) they are not offered. They run fixed commands of the
system: on Windows media keys and LockWorkStation through PowerShell and
rundll32; on macOS osascript, pmset and screencapture; on Linux pactl,
playerctl, loginctl and the first screenshot tool found. The model never
chooses a command line. The same tools serve the instant commands, which
call them through the Tool Gateway without a model.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess  # nosec B404 - fixed argument lists, never a shell
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.instant import reminders
from app.instant.apps import in_container

from .base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata

ACTIONS = ("volume_up", "volume_down", "mute", "play_pause", "next", "previous")
# Windows virtual keys of the media keys; a volume key moves it 2%, so five presses.
_WINDOWS_KEYS = {"volume_up": 175, "volume_down": 174, "mute": 173, "play_pause": 179, "next": 176, "previous": 177}
_PRESSES = {"volume_up": 5, "volume_down": 5}
_DONE = {
    "volume_up": "Volume up.",
    "volume_down": "Volume down.",
    "mute": "Mute toggled.",
    "play_pause": "Play/pause pressed.",
    "next": "Next track.",
    "previous": "Previous track.",
}

EXAMPLES = {
    "media_control": ["volume", "alza", "abbassa", "muto", "pausa", "play", "canzone", "louder", "mute", "pause", "next song"],
    "lock_screen": ["blocca lo schermo", "blocca il pc", "lock the screen", "lock my computer"],
    "take_screenshot": ["screenshot", "cattura lo schermo", "foto dello schermo", "take a screenshot"],
    "set_timer": ["timer", "conto alla rovescia", "countdown"],
    "set_reminder": ["ricordami", "promemoria", "remind me", "reminder"],
    "list_reminders": ["promemoria attivi", "timer attivi", "reminders", "timers"],
}


class SystemCommandError(RuntimeError):
    """The command is not available on this system, or it failed."""


def _run(command: List[str]) -> None:
    try:
        subprocess.run(command, check=True, timeout=15, capture_output=True)  # nosec B603 - fixed argument list
    except FileNotFoundError as exc:
        raise SystemCommandError(f"{command[0]} is not installed.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode(errors="replace").strip()[:200]
        raise SystemCommandError(f"{command[0]} failed{': ' + detail if detail else ''}.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemCommandError(f"{command[0]} did not answer.") from exc


def _powershell(script: str) -> None:
    _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _first(*names: str) -> str:
    for name in names:
        if shutil.which(name):
            return name
    raise SystemCommandError(f"None of {', '.join(names)} is installed.")


def _media(action: str) -> str:
    if action not in ACTIONS:
        raise SystemCommandError(f"Unknown action '{action}': one of {', '.join(ACTIONS)}.")
    if sys.platform == "win32":
        presses = _PRESSES.get(action, 1)
        _powershell(
            "$shell = New-Object -ComObject WScript.Shell; "
            f"1..{presses} | ForEach-Object {{ $shell.SendKeys([char]{_WINDOWS_KEYS[action]}) }}"
        )
    elif sys.platform == "darwin":
        scripts = {
            "volume_up": "set volume output volume ((output volume of (get volume settings)) + 10)",
            "volume_down": "set volume output volume ((output volume of (get volume settings)) - 10)",
            "mute": "set volume output muted (not (output muted of (get volume settings)))",
        }
        if action not in scripts:
            raise SystemCommandError("On macOS only the volume and mute are available.")
        _run(["osascript", "-e", scripts[action]])
    else:
        if action in ("volume_up", "volume_down", "mute"):
            pactl = _first("pactl")
            if action == "mute":
                _run([pactl, "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            else:
                _run([pactl, "set-sink-volume", "@DEFAULT_SINK@", "+10%" if action == "volume_up" else "-10%"])
        else:
            command = {"play_pause": "play-pause", "next": "next", "previous": "previous"}[action]
            _run([_first("playerctl"), command])
    return _DONE[action]


def _lock() -> str:
    if sys.platform == "win32":
        _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif sys.platform == "darwin":
        _run(["pmset", "displaysleepnow"])
    else:
        _run([_first("loginctl"), "lock-session"])
    return "Screen locked."


def _screenshot() -> str:
    from app.agent_engine.guardrails import validate_path
    from app.documents.index import documents_root

    folder = documents_root()
    if not folder.is_dir():
        raise SystemCommandError(f"The working folder {folder} does not exist.")
    target: Path = validate_path(str(folder / f"Screenshot {datetime.now():%Y-%m-%d %H.%M.%S}.png"))
    if sys.platform == "win32":
        quoted = str(target).replace("'", "''")
        _powershell(
            "Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
            "$area = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
            "$image = New-Object System.Drawing.Bitmap $area.Width, $area.Height; "
            "$graphics = [System.Drawing.Graphics]::FromImage($image); "
            "$graphics.CopyFromScreen($area.Left, $area.Top, 0, 0, $image.Size); "
            f"$image.Save('{quoted}', [System.Drawing.Imaging.ImageFormat]::Png)"
        )
    elif sys.platform == "darwin":
        _run(["screencapture", "-x", str(target)])
    else:
        tool = _first("gnome-screenshot", "grim", "scrot", "spectacle")
        arguments = {"gnome-screenshot": ["-f"], "spectacle": ["-b", "-n", "-o"]}.get(tool, [])
        _run([tool, *arguments, str(target)])
    if not target.is_file():
        raise SystemCommandError("The screenshot was not saved.")
    return f"Screenshot saved: {target}"


def _scope() -> Any:
    from app.skills.memory_skill import current_memory_scope

    return current_memory_scope()


def _when(due: datetime) -> str:
    today = datetime.now().date()
    day = "today" if due.date() == today else "tomorrow" if (due.date() - today).days == 1 else f"{due:%Y-%m-%d}"
    return f"{day} at {due:%H:%M}"


async def media_control(action: str) -> str:
    """
    Press a media key of this computer: volume_up, volume_down, mute, play_pause, next, previous.
    """
    return await asyncio.to_thread(_media, action)


async def lock_screen() -> str:
    """
    Lock this computer's screen.
    """
    return await asyncio.to_thread(_lock)


async def take_screenshot() -> str:
    """
    Take a screenshot of this computer and save it in the working folder.
    """
    return await asyncio.to_thread(_screenshot)


async def set_timer(minutes: float, label: str = "") -> str:
    """
    Start a timer: in this many minutes the Nucleo rings and says so.
    """
    scope = _scope()
    due = reminders.due_at(minutes=minutes)
    text = label.strip() or f"Timer of {minutes:g} minutes: time is up."
    reminders.schedule(text, due, scope.session_id, scope.workspace_id)
    return f"Timer set for {minutes:g} minutes (until {due:%H:%M}). A restart of ÆHub forgets it."


async def set_reminder(text: str, minutes: float = 0, at: str = "") -> str:
    """
    Remind the user of something in N minutes, or at a time of day ("18:30").
    """
    scope = _scope()
    due = reminders.due_at(minutes=minutes, at=at)
    reminders.schedule(text, due, scope.session_id, scope.workspace_id)
    return f"Reminder set for {_when(due)}: {text.strip()}. A restart of ÆHub forgets it."


async def list_reminders() -> str:
    """
    List the timers and reminders still waiting.
    """
    waiting = reminders.pending(_scope().workspace_id)
    if not waiting:
        return "No timer or reminder is waiting."
    return "\n".join(f"{_when(item.due)}: {item.text}" for item in waiting)


DESKTOP_TOOLS = [media_control, lock_screen, take_screenshot]
REMINDER_TOOLS = [set_timer, set_reminder, list_reminders]


class SystemSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="system",
            description="Volume, media keys, screen lock and screenshots of this computer; timers and reminders.",
            version="1.0.0",
        )

    @staticmethod
    def desktop() -> bool:
        return not in_container()

    @property
    def tools(self) -> List[Callable[..., Any]]:
        return (DESKTOP_TOOLS if self.desktop() else []) + REMINDER_TOOLS

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        def meta(name: str, description: str, risk: RiskLevel, properties: Dict[str, Any], required: List[str], **extra: Any) -> ToolMetadata:
            return ToolMetadata(
                name=name,
                examples=EXAMPLES[name],
                description=description,
                risk_level=risk,
                permissions_required=["tool:execute:safe"],
                max_runtime=20,
                max_output=2000,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                output_schema={"type": "string"},
                **extra,
            )

        minutes = {"type": "number", "exclusiveMinimum": 0, "maximum": 10080}
        tools = {
            "set_timer": meta("set_timer", "Start a timer of N minutes; the Nucleo rings when it ends.", RiskLevel.LOW, {"minutes": minutes, "label": {"type": "string", "maxLength": 200}}, ["minutes"]),
            "set_reminder": meta(
                "set_reminder",
                "Remind the user of something in N minutes, or at a time of day (at: \"18:30\"). One of minutes or at.",
                RiskLevel.LOW,
                {"text": {"type": "string", "minLength": 1, "maxLength": 200}, "minutes": minutes, "at": {"type": "string", "pattern": "^([01]?[0-9]|2[0-3])(:[0-5][0-9])?$"}},
                ["text"],
            ),
            "list_reminders": meta("list_reminders", "List the timers and reminders still waiting.", RiskLevel.LOW, {}, []),
        }
        if self.desktop():
            tools["media_control"] = meta("media_control", "Press a media key of this computer: volume up/down, mute, play/pause, next, previous track.", RiskLevel.LOW, {"action": {"type": "string", "enum": list(ACTIONS)}}, ["action"])
            tools["lock_screen"] = meta("lock_screen", "Lock this computer's screen.", RiskLevel.LOW, {}, [])
            tools["take_screenshot"] = meta("take_screenshot", "Take a screenshot of this computer, saved as a PNG in the working folder.", RiskLevel.MEDIUM, {}, [], modifies_files=True, filesystem_access=True)
        return tools


def get_skill() -> BaseSkill:
    return SystemSkill()


__all__ = ["ACTIONS", "SystemCommandError", "SystemSkill", "get_skill"] + [tool.__name__ for tool in DESKTOP_TOOLS + REMINDER_TOOLS]
