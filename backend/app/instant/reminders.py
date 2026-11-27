"""
@file backend/app/instant/reminders.py
@description Timers and reminders (N4): "timer di 5 minuti", "ricordami tra 10 minuti di chiamare Marco".

A reminder waits in this process and, when due, publishes "reminder.due" on
the owner's workspace channel: the Nucleo shows it in the conversation, rings
and, when the page is in the background, raises a system notification.

They live in memory: a restart of ÆHub forgets the ones still waiting (the
answer says so). At most MAX_PENDING wait at once, each at most MAX_DELAY
away. A time of day ("alle 18") is the time of the computer ÆHub runs on.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_PENDING = 20
MAX_DELAY = timedelta(days=7)
MAX_TEXT = 200


@dataclass
class Reminder:
    id: str
    text: str
    due: datetime
    session_id: str
    workspace_id: str


_pending: Dict[str, Reminder] = {}
_tasks: Dict[str, "asyncio.Task[None]"] = {}


def due_at(minutes: float = 0, at: str = "", now: Optional[datetime] = None) -> datetime:
    """
    When a reminder is due: in `minutes`, or at "HH:MM" today (tomorrow when
    that time has passed). ValueError for anything out of range.
    """
    now = now or datetime.now()
    if at:
        try:
            hour, _, minute = at.strip().partition(":")
            when = now.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
        except ValueError as exc:
            raise ValueError(f"'{at}' is not a time of day (HH:MM).") from exc
        if when <= now:
            when += timedelta(days=1)
        return when
    if minutes <= 0:
        raise ValueError("A reminder needs a time: minutes from now or a time of day.")
    delay = timedelta(minutes=minutes)
    if delay > MAX_DELAY:
        raise ValueError("A reminder can be at most 7 days away.")
    return now + delay


async def _fire(reminder: Reminder) -> None:
    from app.core.event_bus import event_bus

    try:
        await asyncio.sleep(max(0.0, (reminder.due - datetime.now()).total_seconds()))
        await event_bus.publish(
            reminder.session_id,
            "reminder.due",
            {"id": reminder.id, "text": reminder.text, "due": reminder.due.isoformat(timespec="minutes")},
            workspace_id=reminder.workspace_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a lost reminder is logged, never raised into the loop
        logger.warning("Reminder %s not delivered: %s", reminder.id, exc)
    finally:
        _pending.pop(reminder.id, None)
        _tasks.pop(reminder.id, None)


def schedule(text: str, due: datetime, session_id: str, workspace_id: str) -> Reminder:
    """Wait for `due` in the running event loop, then announce `text`."""
    text = " ".join(text.split())[:MAX_TEXT]
    if not text:
        raise ValueError("A reminder needs a text.")
    if len(_pending) >= MAX_PENDING:
        raise ValueError(f"There are already {MAX_PENDING} reminders waiting.")
    if due - datetime.now() > MAX_DELAY:
        raise ValueError("A reminder can be at most 7 days away.")
    reminder = Reminder(uuid.uuid4().hex[:12], text, due, session_id, workspace_id)
    _pending[reminder.id] = reminder
    _tasks[reminder.id] = asyncio.get_running_loop().create_task(_fire(reminder))
    return reminder


def pending(workspace_id: str) -> List[Reminder]:
    return sorted((item for item in _pending.values() if item.workspace_id == workspace_id), key=lambda item: item.due)


def cancel(reminder_id: str, workspace_id: str) -> bool:
    reminder = _pending.get(reminder_id)
    if reminder is None or reminder.workspace_id != workspace_id:
        return False
    task = _tasks.get(reminder_id)
    if task is not None:
        task.cancel()
    _pending.pop(reminder_id, None)
    return True


def clear() -> None:
    """Forget every reminder (tests)."""
    for task in list(_tasks.values()):
        task.cancel()
    _tasks.clear()
    _pending.clear()


__all__ = ["MAX_PENDING", "Reminder", "cancel", "clear", "due_at", "pending", "schedule"]
