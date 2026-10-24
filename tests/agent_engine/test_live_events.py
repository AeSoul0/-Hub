"""
The engine pushes every run event live (F1): the Nucleo draws the engine at
work from these. Delivery is best effort and never affects the run.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agent_engine import events as events_module
from app.agent_engine.events import LIVE_EVENT_TYPE, EventDispatcher
from app.core.event_bus import EventBus


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    path = tmp_path / "flight.jsonl"
    monkeypatch.setattr(events_module, "FLIGHT_RECORDER_FILE", str(path))
    return path


@pytest.fixture
def bus(monkeypatch):
    monkeypatch.setenv("AEHUB_EVENT_BUS", "memory")
    local = EventBus()
    monkeypatch.setattr("app.core.event_bus.event_bus", local)
    return local


async def _drain() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_an_event_reaches_the_workspace_and_the_session_live(recorder, bus):
    workspace = bus.subscribe_workspace("ws-1")
    session = bus.subscribe("sess-1")

    EventDispatcher().dispatch(
        "tool.proposed",
        run_id="run-1",
        session_id="sess-1",
        workspace_id="ws-1",
        tool="home_set_light",
    )
    await _drain()

    for queue in (workspace, session):
        message = json.loads(queue.get_nowait())
        assert message["type"] == LIVE_EVENT_TYPE
        assert message["data"]["event_type"] == "tool.proposed"
        assert message["data"]["run_id"] == "run-1"
        assert message["data"]["tool"] == "home_set_light"

    # The flight recorder still gets it.
    assert json.loads(recorder.read_text(encoding="utf-8"))["event_type"] == "tool.proposed"


async def test_a_failing_bus_never_reaches_the_run(recorder, monkeypatch):
    async def broken(*args, **kwargs):
        raise ConnectionError("bus down")

    monkeypatch.setattr("app.core.event_bus.event_bus.publish", broken)

    event = EventDispatcher().dispatch(
        "run.started",
        run_id="run-2",
        session_id="sess-1",
        workspace_id="ws-1",
    )
    await _drain()

    assert event.event_type == "run.started"
    assert not events_module._live_tasks


def test_outside_an_event_loop_nothing_is_sent(recorder, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("published without a loop")

    monkeypatch.setattr("app.core.event_bus.event_bus.publish", must_not_run)

    EventDispatcher().dispatch(
        "run.completed",
        run_id="run-3",
        session_id="sess-1",
        workspace_id="ws-1",
    )

    assert "run.completed" in recorder.read_text(encoding="utf-8")
