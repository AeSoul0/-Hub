"""
@file tests/agent_engine/test_conversations.py
@description N6: the Nucleo's past conversations, listed, searched, resumed.

- a command sent with a conversation id runs in "<principal>~<id>"; without
  one, or with an id that is not one, in the principal's own session;
- the list groups the principal's top-level runs by conversation, newest
  first, titled by the first command; the search reads commands and answers;
- one conversation gives its turns oldest first, with the answer, a line for
  a stopped run, and the error of a failed one;
- subagents, other principals and other workspaces are never listed.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agents import orchestrator
from app.api import conversations
from app.core.security import Principal, RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun

OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-n6")
START = datetime(2026, 11, 27, 9, 0)


def test_the_session_of_a_conversation():
    assert orchestrator.conversation_session("owner", "") == "owner"
    assert orchestrator.conversation_session("owner", "c-1") == "owner~c-1"
    assert orchestrator.conversation_session("owner", "../etc") == "owner"
    assert orchestrator.conversation_session("owner", "x" * 65) == "owner"


@pytest.fixture
def rows(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.db.SessionLocal", db_session_factory)
    minute = iter(range(1000))

    def add(session_id, task, result=None, *, status="completed", error=None, principal="owner",
            workspace="workspace-n6", parent=None, channel="text"):
        snapshot = {
            "workspace_id": workspace,
            "parent_run_id": parent,
            "current_state": {"worker_context": {"task": {"description": task, "input_channel": channel}}},
        }
        with db_session_factory() as db:
            db.add(
                DbAgentRun(
                    session_id=session_id,
                    principal_id=principal,
                    input_data=json.dumps(snapshot),
                    status=status,
                    result=None if result is None else json.dumps(result),
                    error=error,
                    created_at=START + timedelta(minutes=next(minute)),
                )
            )
            db.commit()

    return add


def _list(q=None):
    return asyncio.run(conversations.list_conversations(q=q, limit=50, principal=OWNER))


def _get(conversation_id):
    return asyncio.run(conversations.get_conversation(conversation_id, principal=OWNER))


def test_conversations_are_listed_searched_and_read(rows):
    rows("owner", "Che ore sono?", "Sono le 9.")
    rows("owner~trip", "Organizza il viaggio a Lisbona", "Ecco un piano in tre giorni.", channel="voice")
    rows("owner~trip", "Aggiungi un museo", {"status": "CANCELLED", "reason": "by the user"}, status="cancelled")
    rows("owner~trip", "child work", "secret", parent="run-parent")
    rows("owner~notes", "Riassumi le note", None, status="failed", error="model unreachable")
    rows("owner~trip", "not mine", "x", principal="guest")
    rows("guest~trip", "not mine either", "x", principal="guest")
    rows("owner~elsewhere", "other workspace", "x", workspace="other")
    rows("owner~bad id!", "not a conversation", "x")

    listed = _list()
    assert [item["id"] for item in listed["conversations"]] == ["notes", "trip", ""]
    trip = listed["conversations"][1]
    assert (trip["title"], trip["turns"], trip["match"]) == ("Organizza il viaggio a Lisbona", 2, None)

    assert [item["id"] for item in _list("LISBONA")["conversations"]] == ["trip"]
    # The answers are searched too, and the turn that matched is shown.
    found = _list("ore sono")["conversations"]
    assert [(item["id"], item["match"]) for item in found] == [("", "Che ore sono?")]
    assert _list("piano in tre")["conversations"][0]["match"] == "Organizza il viaggio a Lisbona"
    assert _list("secret")["total"] == 0

    turns = _get("trip")["turns"]
    assert [(turn["task"], turn["answer"], turn["channel"]) for turn in turns] == [
        ("Organizza il viaggio a Lisbona", "Ecco un piano in tre giorni.", "voice"),
        ("Aggiungi un museo", "Command stopped.", "text"),
    ]
    assert _get("notes")["turns"][0]["answer"] == "Error: model unreachable"
    assert _get("_")["turns"][0]["task"] == "Che ore sono?"

    for missing in ("nothing-here", "bad id!", "elsewhere"):
        with pytest.raises(HTTPException) as error:
            _get(missing)
        assert error.value.status_code == 404


def test_a_command_goes_on_in_its_conversation(monkeypatch):
    seen = []

    async def answer(text, system_prompt, ui_context, session_id, principal, **kwargs):
        seen.append(session_id)
        return {"transcription": "ok"}

    monkeypatch.setattr(orchestrator, "generate_ai_response", answer)
    monkeypatch.setattr("app.core.security.resolve_principal", lambda request, db: OWNER)

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("app.core.db.SessionLocal", Session)

    async def ask(conversation):
        return await orchestrator.process_orchestration_text(
            request=SimpleNamespace(), text="ciao", ui_context="", role="", delivery="live",
            command_id="c1", conversation=conversation, image=None, x_session_id="ignored",
        )

    asyncio.run(ask("trip"))
    asyncio.run(ask(""))
    asyncio.run(ask("no way/../"))
    assert seen == ["owner~trip", "owner", "owner"]

