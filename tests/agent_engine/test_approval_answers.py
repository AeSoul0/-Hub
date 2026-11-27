"""
@file tests/agent_engine/test_approval_answers.py
@description Approvals in a word, by voice or typed (ADR-037).

- a run that waits on the owner answers with one short question, not with
  its state;
- while an approval is pending, "sì", "vai pure", "no", "annulla", "yes"…
  decide the oldest one through the same path as the button, and the reply
  is a few words;
- anything longer, or a yes with nothing pending, goes on as before.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_engine.application import AgentEngine
from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.runtime import AgentRuntime
from app.agents import orchestrator
from app.api import approvals as approvals_api
from app.core.runtime_config import replace_stored
from app.core.security import Principal, RoleEnum
from app.instant.approvals import REPLIES, approval_question, recognize_decision, try_decision
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata

SESSION_ID = "session-answers"
OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-answers")


class TrashSkill(BaseSkill):
    """One HIGH tool with a path, like delete_path."""

    def __init__(self) -> None:
        self.calls: list = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="trash", description="Deletes files.")

    @property
    def tools(self):
        def delete_path(path: str) -> str:
            self.calls.append(path)
            return f"Deleted {path}."

        return [delete_path]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "delete_path": ToolMetadata(
                name="delete_path",
                description="Delete a file.",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            )
        }


@pytest.fixture(autouse=True)
def italian():
    replace_stored({"AEHUB_UI_LANGUAGE": "it"})
    yield
    replace_stored({})


@pytest.fixture
def engine(agent_infrastructure, fake_model):
    skill = TrashSkill()
    agent_infrastructure.use_skills(skill)

    def build(paths=("C:\\Users\\me\\Documenti\\vecchio.txt",)) -> AgentEngine:
        calls = [fake_model.function_call(f"call_{index}", "delete_path", {"path": path}) for index, path in enumerate(paths)]
        return AgentEngine(
            model_provider=fake_model.adapter(calls),
            checker_provider=fake_model.checker([]),
            runtime=AgentRuntime(),
        )

    build.skill = skill
    return build


async def ask(text: str, channel: str = "voice") -> Dict[str, Any]:
    with patch.object(orchestrator, "speak", AsyncMock(return_value=("", ""))):
        return await orchestrator.generate_ai_response(text, "", "", SESSION_ID, principal=OWNER, input_channel=channel)


async def park(engine: AgentEngine) -> Dict[str, Any]:
    """Ask through the orchestrator until the run waits on the owner."""
    with patch.object(orchestrator, "get_aurora_app", AsyncMock(return_value=engine)):
        return await ask("Elimina vecchio.txt dai documenti")


# ==============================================================================
# WHAT COUNTS AS A YES OR A NO
# ==============================================================================


@pytest.mark.parametrize(
    "text, expected",
    [
        ("sì", ("allow", "it")),
        ("Sì.", ("allow", "it")),
        ("Aurora, vai pure", ("allow", "it")),
        ("ok procedi per favore", ("allow", "it")),
        ("consenti", ("allow", "it")),
        ("Yes, go ahead", ("allow", "en")),
        ("go ahead", ("allow", "en")),
        ("yes please", ("allow", "en")),
        ("no", ("deny", "it")),
        ("No, lascia stare.", ("deny", "it")),
        ("annulla", ("deny", "it")),
        ("don't", ("deny", "en")),
        ("cancel", ("deny", "en")),
    ],
)
def test_a_yes_or_a_no(text, expected):
    assert recognize_decision(text, "it") == expected


def test_anything_longer_is_not_an_answer():
    for text in (
        "sì, ma prima dimmi cosa c'è dentro",
        "no, cerca invece il file nuovo",
        "apri Spotify",
        "elimina anche l'altro",
        "",
    ):
        assert recognize_decision(text, "it") is None


def test_a_shared_word_follows_the_interface_language():
    assert recognize_decision("ok", "en") == ("allow", "en")
    assert recognize_decision("no", "en") == ("deny", "en")
    assert recognize_decision("no", "it") == ("deny", "it")


def test_the_question_is_short_and_names_the_file():
    # N5: deleting and overwriting ask for their own words.
    assert approval_question("delete_path", {"path": "C:\\Users\\me\\Documenti\\vecchio.txt"}, "it") == (
        "Posso eliminare vecchio.txt? Per confermare di' «sì, elimina», altrimenti no."
    )
    assert approval_question("replace_file", {"path": "/home/me/piano.md", "content": "x"}, "en") == (
        'May I overwrite piano.md? To confirm say "yes, overwrite", otherwise no.'
    )
    assert approval_question("write_file", {"path": "/home/me/nuovo.md", "content": "x"}, "it") == "Posso scrivere nuovo.md? Sì o no."
    assert approval_question("execute_shell_script", {"command": "ls"}, "it") == "Posso eseguire un comando nella sandbox? Sì o no."
    assert approval_question("mcp_tool_x", {}, "it") == "Posso usare mcp tool x? Sì o no."
    assert approval_question("mcp_tool_x", {"query": "meteo"}, "en") == "May I use mcp tool x on meteo? Yes or no."


# ==============================================================================
# THROUGH THE ORCHESTRATOR
# ==============================================================================


async def test_a_waiting_run_asks_one_short_question(engine):
    reply = await park(engine())

    assert reply["transcription"] == "Posso eliminare vecchio.txt? Per confermare di' «sì, elimina», altrimenti no."
    assert reply["awaiting_approval"] is True
    assert engine.skill.calls == []


async def test_a_spoken_yes_decides_and_the_run_goes_on(engine, agent_infrastructure):
    await park(engine())
    [pending] = await ApprovalManager.list_pending(OWNER.workspace_id)

    with patch.object(approvals_api, "_schedule_resume") as schedule:
        # N5: a plain yes does not delete: the words are asked again.
        again = await ask("Aurora, sì")
        assert again["transcription"] == "Per questo serve «sì, elimina». Lo confermi?"
        assert again["decision"] is None
        assert len(await ApprovalManager.list_pending(OWNER.workspace_id)) == 1
        # Something else that is not an answer goes to the engine.
        assert await try_decision("sovrascrivi", OWNER, "it") is None
        reply = await ask("Aurora, sì, elimina")

    assert reply["transcription"] in REPLIES["it"]["allow"]
    assert reply["decision"] == "allow" and reply["instant"]["tool"] == "approval"
    assert await ApprovalManager.list_pending(OWNER.workspace_id) == []
    decided = [data for _, kind, data in agent_infrastructure.published if kind == "approval.decided"]
    assert decided == [{"approval_id": pending["id"], "run_id": pending["run_id"], "decision": "ALLOW"}]
    schedule.assert_called_once()


async def test_a_typed_no_denies(engine, agent_infrastructure):
    await park(engine())

    with patch.object(approvals_api, "_schedule_resume"):
        reply = await ask("no, lascia stare", channel="text")

    assert reply["transcription"] in REPLIES["it"]["deny"]
    decided = [data["decision"] for _, kind, data in agent_infrastructure.published if kind == "approval.decided"]
    assert decided == ["DENY"]
    assert engine.skill.calls == []


async def test_the_oldest_is_decided_and_the_others_are_counted(engine):
    await park(engine())
    await park(engine(paths=("C:\\Users\\me\\Documenti\\altro.txt",)))
    first, second = await ApprovalManager.list_pending(OWNER.workspace_id)

    with patch.object(approvals_api, "_schedule_resume"):
        reply = await ask("elimina")

    assert reply["transcription"].endswith("Ne resta un'altra.")
    assert [item["id"] for item in await ApprovalManager.list_pending(OWNER.workspace_id)] == [second["id"]]


async def test_a_plain_yes_deletes_when_the_owner_turned_the_words_off(engine, monkeypatch):
    monkeypatch.setenv("AEHUB_CONFIRM_DELETIONS", "off")
    reply = await park(engine())
    assert reply["transcription"] == "Posso eliminare vecchio.txt? Sì o no."
    with patch.object(approvals_api, "_schedule_resume"):
        assert (await ask("sì"))["decision"] == "allow"


async def test_a_yes_with_nothing_pending_goes_on_as_before(agent_infrastructure):
    assert await try_decision("sì", OWNER, "it") is None
