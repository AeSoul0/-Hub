"""
@file tests/agent_engine/test_system_skill.py
@description N4: the computer's own controls, and timers and reminders.

- the instant sentences: volume, mute, play/pause, next/previous, screen
  lock, screenshot, timers and reminders, in Italian and English, and what
  stays with the engine;
- the fixed commands of each system (Windows, macOS, Linux), never a shell;
  inside a container the computer's controls are not offered;
- a reminder waits, then publishes reminder.due on the owner's workspace;
- end to end: "timer di 1 minuto" answers at once through the Tool Gateway.
"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock

import pytest

from app.agents import orchestrator
from app.core.security import Principal, RoleEnum
from app.instant import reminders
from app.instant.matcher import match
from app.skills import system_skill
from app.skills.memory_skill import clear_memory_context, set_memory_context
from app.skills.system_skill import SystemSkill

OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-n4")


@pytest.fixture(autouse=True)
def no_reminders():
    reminders.clear()
    yield
    reminders.clear()


@pytest.mark.parametrize(
    "sentence, tool, arguments, language",
    [
        ("Alza il volume", "media_control", {"action": "volume_up"}, "it"),
        ("abbassa il volume per favore", "media_control", {"action": "volume_down"}, "it"),
        ("togli l'audio", "media_control", {"action": "mute"}, "it"),
        ("Aurora, pausa", "media_control", {"action": "play_pause"}, "it"),
        ("prossima canzone", "media_control", {"action": "next"}, "it"),
        ("previous song", "media_control", {"action": "previous"}, "en"),
        ("blocca lo schermo", "lock_screen", {}, "it"),
        ("take a screenshot", "take_screenshot", {}, "en"),
        ("metti un timer di 5 minuti", "set_timer", {"minutes": 5.0}, "it"),
        ("timer di dieci minuti", "set_timer", {"minutes": 10}, "it"),
        ("set a timer for 90 seconds", "set_timer", {"minutes": 1.5}, "en"),
        ("Ricordami tra 10 minuti di chiamare Marco", "set_reminder", {"text": "chiamare Marco", "minutes": 10.0}, "it"),
        ("ricordami fra mezz'ora di uscire", "set_reminder", {"text": "uscire", "minutes": 30.0}, "it"),
        ("ricordami alle 18:30 di comprare il pane e il latte", "set_reminder", {"text": "comprare il pane e il latte", "at": "18:30"}, "it"),
        ("remind me at 7 to water the plants", "set_reminder", {"text": "water the plants", "at": "07:00"}, "en"),
    ],
)
def test_the_computer_controls_and_reminders_are_instant(sentence, tool, arguments, language):
    command = match(sentence)
    assert command is not None
    assert (command.tool, command.arguments, command.language) == (tool, arguments, language)


@pytest.mark.parametrize(
    "sentence",
    [
        "alza il volume e apri spotify",
        "metti un timer",
        "ricordami di chiamare Marco",
        "ricordami tra 8 giorni di pagare",
        "ricordami alle 25 di dormire",
        "che volume c'è?",
    ],
)
def test_the_rest_goes_to_the_engine(sentence):
    assert match(sentence) is None


def _record(monkeypatch, platform: str) -> List[List[str]]:
    calls: List[List[str]] = []

    def run(command, **kwargs):
        assert isinstance(command, list) and "shell" not in kwargs
        calls.append(command)
        if command[0] in ("screencapture", "grim") or "Save(" in command[-1]:
            target = command[-1] if command[0] != "powershell" else command[-1].split("Save('")[1].split("'")[0]
            open(target, "wb").write(b"png")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(system_skill.subprocess, "run", run)
    monkeypatch.setattr(system_skill.sys, "platform", platform)
    monkeypatch.setattr(system_skill.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("pactl", "playerctl", "loginctl", "grim") else None)
    return calls


def test_each_system_runs_its_own_fixed_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("AEHUB_ALLOWED_DIRS", str(tmp_path))

    calls = _record(monkeypatch, "win32")
    assert asyncio.run(system_skill.media_control("volume_up")) == "Volume up."
    assert calls[-1][0] == "powershell" and "[char]175" in calls[-1][-1] and "1..5" in calls[-1][-1]
    asyncio.run(system_skill.lock_screen())
    assert calls[-1] == ["rundll32.exe", "user32.dll,LockWorkStation"]
    saved = asyncio.run(system_skill.take_screenshot())
    assert saved.startswith(f"Screenshot saved: {tmp_path}") and saved.endswith(".png")

    calls = _record(monkeypatch, "darwin")
    asyncio.run(system_skill.media_control("mute"))
    assert calls[-1][0] == "osascript"
    with pytest.raises(system_skill.SystemCommandError):
        asyncio.run(system_skill.media_control("next"))

    calls = _record(monkeypatch, "linux")
    asyncio.run(system_skill.media_control("volume_down"))
    asyncio.run(system_skill.media_control("play_pause"))
    asyncio.run(system_skill.lock_screen())
    assert calls == [
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
        ["playerctl", "play-pause"],
        ["loginctl", "lock-session"],
    ]
    with pytest.raises(system_skill.SystemCommandError):
        asyncio.run(system_skill.media_control("rm -rf /"))


def test_in_a_container_only_timers_and_reminders(monkeypatch):
    monkeypatch.setattr(system_skill, "in_container", lambda: True)
    assert sorted(SystemSkill().get_tool_metadata()) == ["list_reminders", "set_reminder", "set_timer"]
    monkeypatch.setattr(system_skill, "in_container", lambda: False)
    tools = SystemSkill().get_tool_metadata()
    assert {name: meta.risk_level.value for name, meta in tools.items()} == {
        "set_timer": "low",
        "set_reminder": "low",
        "list_reminders": "low",
        "media_control": "low",
        "lock_screen": "low",
        "take_screenshot": "medium",
    }


def test_a_reminder_rings_on_the_owners_workspace(monkeypatch):
    published: List[Any] = []

    async def publish(session_id, event_type, data, workspace_id=""):
        published.append((session_id, event_type, data["text"], workspace_id))

    monkeypatch.setattr("app.core.event_bus.event_bus.publish", publish)

    async def scenario():
        set_memory_context(session_id="owner", workspace_id=OWNER.workspace_id, principal_id=OWNER.id)
        try:
            answer = await system_skill.set_reminder("chiamare Marco", minutes=10)
            assert "Reminder set for today" in answer or "Reminder set for tomorrow" in answer
            assert "chiamare Marco" in await system_skill.list_reminders()
        finally:
            clear_memory_context()
        # One due now: it rings at once.
        reminders.schedule("Timer finito", datetime.now(), "owner", OWNER.workspace_id)
        await asyncio.sleep(0.05)
        assert [item.text for item in reminders.pending(OWNER.workspace_id)] == ["chiamare Marco"]
        assert reminders.cancel(reminders.pending(OWNER.workspace_id)[0].id, OWNER.workspace_id)
        assert reminders.pending(OWNER.workspace_id) == []

    asyncio.run(scenario())
    assert published == [("owner", "reminder.due", "Timer finito", OWNER.workspace_id)]


def test_reminder_times_and_limits():
    now = datetime(2026, 11, 27, 19, 0)
    assert reminders.due_at(at="18:30", now=now) == datetime(2026, 11, 28, 18, 30)
    assert reminders.due_at(at="20", now=now) == datetime(2026, 11, 27, 20, 0)
    assert reminders.due_at(minutes=15, now=now) == now + timedelta(minutes=15)
    for wrong in ({"minutes": 0}, {"minutes": 60 * 24 * 8}, {"at": "noon"}):
        with pytest.raises(ValueError):
            reminders.due_at(now=now, **wrong)


def test_a_timer_answers_at_once_through_the_gateway(agent_infrastructure, monkeypatch):
    registry = agent_infrastructure.use_skills(SystemSkill())
    monkeypatch.setattr("app.skills.registry.skill_registry", registry)
    engine = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "From the engine."}]})
    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=SimpleNamespace(ainvoke=engine)))
    monkeypatch.setattr(orchestrator, "speak", AsyncMock(return_value=("", "")))
    monkeypatch.setattr("app.core.event_bus.event_bus.publish", AsyncMock())

    async def ask():
        reply = await orchestrator.generate_ai_response("timer di 1 minuto", "", "", OWNER.id, OWNER)
        return reply, [item.text for item in reminders.pending(OWNER.workspace_id)]

    reply, waiting = asyncio.run(ask())
    assert reply["transcription"] == "Timer di 1 minuto avviato."
    assert reply["instant"]["tool"] == "set_timer" and reply["instant"]["success"] is True
    assert waiting == ["Timer of 1 minutes: time is up."]
    engine.assert_not_awaited()
