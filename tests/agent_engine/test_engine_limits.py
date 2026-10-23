"""
@file tests/agent_engine/test_engine_limits.py
@description M9 exit tests: the known limits of the agent engine.

- calls proposed in the same turn as a call parked for approval run after
  the decision instead of being lost;
- every run has a time limit on active execution, and the wait for an
  approval does not count;
- per-run limits on failed tool calls and on modified files;
- subagents receive the tools the PolicyEngine allows them, with the
  budget and the untrusted taint of their parent run.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.agent_engine.application import AgentEngine
from app.agent_engine.approval.manager import ApprovalManager
from app.agent_engine.control import run_registry
from app.agent_engine import runtime as runtime_module
from app.agent_engine.errors import TaskTimeoutError
from app.agent_engine.resources import PROFILES, TaskClass
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.domain.models.runtime_state import AgentRun as DbAgentRun
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


SESSION_ID = "session-m9"
WORKSPACE_ID = "workspace-m9"


# ==============================================================================
# TEST DOUBLES
# ==============================================================================


def _schema(**properties: Any) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class WorkSkill(BaseSkill):
    """
    LOW, HIGH, failing, slow, file-writing and untrusted-output tools.
    """

    def __init__(self) -> None:
        self.calls: List[str] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="work", description="Work tools.")

    @property
    def tools(self):
        def note(text: str) -> str:
            self.calls.append(f"note:{text}")
            return f"noted {text}"

        def delete_record(record_id: str) -> str:
            self.calls.append(f"delete:{record_id}")
            return f"deleted {record_id}"

        def run_cleanup(scope: str) -> str:
            self.calls.append(f"cleanup:{scope}")
            return f"cleaned {scope}"

        def broken(reason: str) -> str:
            self.calls.append(f"broken:{reason}")
            raise RuntimeError(f"broken: {reason}")

        async def slow(seconds: float) -> str:
            await asyncio.sleep(seconds)
            self.calls.append("slow")
            return "slow done"

        def write_file(path: str, text: str) -> str:
            self.calls.append(f"write:{path}")
            return f"wrote {path}"

        def fetch_page(url: str) -> str:
            self.calls.append(f"fetch:{url}")
            return "Page text."

        return [note, delete_record, run_cleanup, broken, slow, write_file, fetch_page]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "note": ToolMetadata(
                name="note",
                description="Write a note.",
                input_schema=_schema(text={"type": "string"}),
            ),
            "delete_record": ToolMetadata(
                name="delete_record",
                description="Permanently delete one record.",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                input_schema=_schema(record_id={"type": "string"}),
            ),
            # HIGH without requires_approval: it only needs approval once the
            # run has read untrusted content.
            "run_cleanup": ToolMetadata(
                name="run_cleanup",
                description="Clean up a scope.",
                risk_level=RiskLevel.HIGH,
                input_schema=_schema(scope={"type": "string"}),
            ),
            "broken": ToolMetadata(
                name="broken",
                description="Always fails.",
                input_schema=_schema(reason={"type": "string"}),
            ),
            "slow": ToolMetadata(
                name="slow",
                description="Takes a while.",
                input_schema=_schema(seconds={"type": "number"}),
            ),
            "write_file": ToolMetadata(
                name="write_file",
                description="Write a file.",
                modifies_files=True,
                input_schema=_schema(path={"type": "string"}, text={"type": "string"}),
            ),
            "fetch_page": ToolMetadata(
                name="fetch_page",
                description="Fetch a web page.",
                untrusted_output=True,
                input_schema=_schema(url={"type": "string"}),
            ),
        }


def _calls(*calls: Any) -> Any:
    """
    One Responses API turn proposing several function calls.
    """
    return SimpleNamespace(
        id="resp_multi",
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id=call_id,
                name=name,
                arguments=json.dumps(arguments),
            )
            for call_id, name, arguments in calls
        ],
        usage=None,
    )


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def work(agent_infrastructure) -> WorkSkill:
    skill = WorkSkill()
    agent_infrastructure.use_skills(skill)
    return skill


@pytest.fixture(autouse=True)
def enough_memory(monkeypatch):
    # ResourceManager checks the free RAM of the machine running the tests.
    monkeypatch.setattr(
        runtime_module.ResourceManager,
        "allocate",
        classmethod(lambda cls, description: PROFILES[TaskClass.STANDARD]),
    )


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    run_registry.resume()
    for live in run_registry.active():
        run_registry.unregister(live.run_id)


@pytest.fixture
def admin() -> Principal:
    # HIGH tools need EXECUTE_SENSITIVE_TOOL, which USER does not have.
    return Principal(id="admin-m9", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)


def _engine(fake_model, worker_script: List[Any], checker_script: List[Any]) -> AgentEngine:
    worker = fake_model.adapter(worker_script)
    engine = AgentEngine(
        model_provider=worker,
        checker_provider=fake_model.checker(checker_script),
        runtime=AgentRuntime(),
    )
    engine.model_requests = worker._client.responses.requests
    return engine


def _row(db_session_factory, run_id: str) -> DbAgentRun:
    with db_session_factory() as db:
        return db.query(DbAgentRun).filter(DbAgentRun.id == run_id).one()


def _snapshot(db_session_factory, run_id: str) -> Dict[str, Any]:
    return json.loads(_row(db_session_factory, run_id).input_data)


async def _decide_and_resume(
    engine: AgentEngine,
    parked: Dict[str, Any],
    decision: str,
    principal: Principal,
) -> Any:
    await ApprovalManager.grant_approval(
        parked["approval_id"],
        decision,
        decided_by=principal.id,
        workspace_id=WORKSPACE_ID,
    )

    return await engine.resume(
        run_id=parked["run_id"],
        session_id=SESSION_ID,
        principal=principal,
    )


def _outputs(request: Dict[str, Any]) -> List[str]:
    return [
        item["call_id"]
        for item in request["input"]
        if item.get("type") == "function_call_output"
    ]


# ==============================================================================
# CALLS OF THE SAME TURN SURVIVE AN APPROVAL WAIT
# ==============================================================================


async def test_calls_after_a_parked_one_run_after_approval(
    work, admin, fake_model, db_session_factory
):
    engine = _engine(
        fake_model,
        [
            _calls(
                ("call_a", "note", {"text": "a"}),
                ("call_del", "delete_record", {"record_id": "r1"}),
                ("call_b", "note", {"text": "b"}),
            ),
            fake_model.text("All done."),
        ],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Note, delete, note.", principal=admin)
    parked = result["messages"][0].content

    assert parked["status"] == "WAITING_APPROVAL"
    assert work.calls == ["note:a"]

    context = _snapshot(db_session_factory, parked["run_id"])["current_state"]["worker_context"]
    assert context["pending_tool_call"]["tool_call_id"] == "call_del"
    assert [call["tool_call_id"] for call in context["queued_tool_calls"]] == ["call_b"]

    outcome = await _decide_and_resume(engine, parked, "ALLOW", admin)

    assert outcome == "All done."
    assert work.calls == ["note:a", "delete:r1", "note:b"]

    # The model sees every call of the turn answered, in order.
    assert _outputs(engine.model_requests[1]) == ["call_a", "call_del", "call_b"]

    context = _snapshot(db_session_factory, parked["run_id"])["current_state"]["worker_context"]
    assert context["queued_tool_calls"] == []


async def test_a_denial_drops_the_queued_calls(work, admin, fake_model, db_session_factory):
    engine = _engine(
        fake_model,
        [
            _calls(
                ("call_del", "delete_record", {"record_id": "r1"}),
                ("call_b", "note", {"text": "b"}),
            ),
        ],
        [],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delete, then note.", principal=admin)
    parked = result["messages"][0].content

    outcome = await _decide_and_resume(engine, parked, "DENY", admin)

    assert outcome["status"] == "DENIED"
    assert work.calls == []

    context = _snapshot(db_session_factory, parked["run_id"])["current_state"]["worker_context"]
    assert context["queued_tool_calls"] == []


async def test_a_queued_high_call_parks_the_run_again(work, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            _calls(
                ("call_r1", "delete_record", {"record_id": "r1"}),
                ("call_r2", "delete_record", {"record_id": "r2"}),
            ),
            fake_model.text("Both deleted."),
        ],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delete r1 and r2.", principal=admin)
    first = result["messages"][0].content

    second = await _decide_and_resume(engine, first, "ALLOW", admin)

    assert second["status"] == "WAITING_APPROVAL"
    assert second["run_id"] == first["run_id"]
    assert second["approval_id"] != first["approval_id"]
    assert work.calls == ["delete:r1"]

    outcome = await _decide_and_resume(engine, second, "ALLOW", admin)

    assert outcome == "Both deleted."
    assert work.calls == ["delete:r1", "delete:r2"]
    assert _outputs(engine.model_requests[1]) == ["call_r1", "call_r2"]


# ==============================================================================
# TIME LIMIT ON ACTIVE EXECUTION
# ==============================================================================


async def test_default_time_limit_stops_a_run(
    work, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_TIMEOUT_SECONDS", "0.2")

    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_slow", "slow", {"seconds": 0.4}),
            fake_model.text("Never reached."),
        ],
        [],
    )

    with pytest.raises(TaskTimeoutError):
        await engine.run(session_id=SESSION_ID, task="Do the slow thing.", principal=admin)

    # The tool ran; the model was not called again after the limit.
    assert work.calls == ["slow"]
    assert len(engine.model_requests) == 1


async def test_waiting_for_approval_does_not_count_toward_the_limit(
    work, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_TIMEOUT_SECONDS", "60")

    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_del", "delete_record", {"record_id": "r1"}),
            fake_model.text("Deleted."),
        ],
        [fake_model.accept()],
    )

    result = await engine.run(session_id=SESSION_ID, task="Delete r1.", principal=admin)
    parked = result["messages"][0].content

    # The approval arrives two hours after the run started.
    with db_session_factory() as db:
        row = db.query(DbAgentRun).filter(DbAgentRun.id == parked["run_id"]).one()
        started = datetime.utcnow() - timedelta(hours=2)
        snapshot = json.loads(row.input_data)
        snapshot["created_at"] = started.isoformat()
        row.input_data = json.dumps(snapshot)
        row.created_at = started
        db.commit()

    outcome = await _decide_and_resume(engine, parked, "ALLOW", admin)

    assert outcome == "Deleted."
    assert _snapshot(db_session_factory, parked["run_id"])["usage"]["active_seconds"] < 60


# ==============================================================================
# FAILED TOOL CALLS AND MODIFIED FILES
# ==============================================================================


async def test_repeated_tool_failures_stop_the_run(
    work, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_FAILED_TOOL_CALLS", "2")

    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "broken", {"reason": "one"}),
            fake_model.function_call("call_2", "broken", {"reason": "two"}),
            fake_model.text("Never reached."),
        ],
        [],
    )

    result = await engine.run(session_id=SESSION_ID, task="Keep trying.", principal=admin)
    outcome = result["messages"][0].content

    assert outcome["status"] == "LIMIT_EXCEEDED"
    assert outcome["reason"] == "Failed tool calls limit reached: 2 of 2."
    assert len(engine.model_requests) == 2

    snapshot = _snapshot(db_session_factory, result["run_id"])
    assert snapshot["usage"]["failed_tool_calls"] == 2
    assert _row(db_session_factory, result["run_id"]).status.lower() == "failed"


async def test_modified_files_limit_refuses_a_new_file(
    work, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_FILES_MODIFIED", "2")

    engine = _engine(
        fake_model,
        [
            _calls(
                ("call_a", "write_file", {"path": "a.txt", "text": "1"}),
                ("call_b", "write_file", {"path": "b.txt", "text": "1"}),
                # Same file again: still two files.
                ("call_a2", "write_file", {"path": "a.txt", "text": "2"}),
                ("call_c", "write_file", {"path": "c.txt", "text": "1"}),
            ),
        ],
        [],
    )

    result = await engine.run(session_id=SESSION_ID, task="Write files.", principal=admin)
    outcome = result["messages"][0].content

    assert outcome["status"] == "LIMIT_EXCEEDED"
    assert "'write_file' was not run" in outcome["reason"]
    assert work.calls == ["write:a.txt", "write:b.txt", "write:a.txt"]

    usage = _snapshot(db_session_factory, result["run_id"])["usage"]
    assert usage["files_modified"] == ["a.txt", "b.txt"]


# ==============================================================================
# SUBAGENTS
# ==============================================================================


def _tool_names(request: Dict[str, Any]) -> List[str]:
    return sorted(tool["name"] for tool in request.get("tools") or [])


async def test_subagent_gets_only_its_delegated_tools(work, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_n", "note", {"text": "sub"}),
            fake_model.text("Subtask done."),
        ],
        [fake_model.accept()],
    )

    outcome = await engine.spawn_subagent(
        parent_run_id=None,
        session_id=SESSION_ID,
        task="Write a note.",
        role="research",
        budget=1.0,
        principal=admin,
        allowed_tools=["note", "fetch_page"],
    )

    assert outcome["result"] == "Subtask done."
    assert work.calls == ["note:sub"]
    assert _tool_names(engine.model_requests[0]) == ["fetch_page", "note"]


async def test_subagent_cannot_call_a_tool_it_was_not_delegated(work, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_c", "run_cleanup", {"scope": "all"}),
            fake_model.text("Could not clean up."),
        ],
        [fake_model.accept()],
    )

    outcome = await engine.spawn_subagent(
        parent_run_id=None,
        session_id=SESSION_ID,
        task="Clean up.",
        role="research",
        budget=1.0,
        principal=admin,
        allowed_tools=["note"],
    )

    assert outcome["result"] == "Could not clean up."
    assert work.calls == []


async def test_untainted_subagent_runs_a_high_tool_its_role_allows(work, admin, fake_model):
    # Control for the next test: without a tainted parent the same HIGH call
    # (no requires_approval) runs for an ADMIN.
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_c", "run_cleanup", {"scope": "tmp"}),
            fake_model.text("Cleaned."),
        ],
        [fake_model.accept()],
    )

    outcome = await engine.spawn_subagent(
        parent_run_id=None,
        session_id=SESSION_ID,
        task="Clean up the temporary files.",
        role="research",
        budget=1.0,
        principal=admin,
    )

    assert outcome["result"] == "Cleaned."
    assert work.calls == ["cleanup:tmp"]


async def test_subagent_inherits_the_parent_taint_and_budget(
    work, admin, fake_model, db_session_factory, monkeypatch
):
    monkeypatch.setenv("AEHUB_RUN_MAX_COST", "100")
    monkeypatch.setenv("AEHUB_MONTHLY_BUDGET", "1000")
    monkeypatch.setenv(
        "AEHUB_MODEL_PRICES",
        json.dumps({"fake-model": {"input": 1_000_000, "output": 1_000_000}}),
    )

    parent = _engine(
        fake_model,
        [
            fake_model.function_call("call_f", "fetch_page", {"url": "https://example.com"}, usage=(30, 10)),
            fake_model.text("Read it."),
        ],
        [fake_model.accept()],
    )

    parent_result = await parent.run(session_id=SESSION_ID, task="Read the page.", principal=admin)
    parent_run_id = parent_result["run_id"]
    parent_cost = _snapshot(db_session_factory, parent_run_id)["usage"]["cost"]
    assert parent_cost >= 40

    child = _engine(
        fake_model,
        [fake_model.function_call("call_c", "run_cleanup", {"scope": "tmp"})],
        [],
    )

    outcome = await child.spawn_subagent(
        parent_run_id=parent_run_id,
        session_id=SESSION_ID,
        task="Clean up the temporary files.",
        role="research",
        budget=1000.0,
        principal=admin,
    )

    # A HIGH call after untrusted content needs approval, in the child too.
    assert outcome["result"]["status"] == "WAITING_APPROVAL"
    assert work.calls == ["fetch:https://example.com"]

    child_context = _snapshot(db_session_factory, outcome["child_run_id"])["current_state"][
        "worker_context"
    ]
    assert child_context["untrusted_context"] is True
    assert child_context["max_cost"] == pytest.approx(100 - parent_cost)


async def test_subagent_needs_a_parent_of_the_same_principal(work, admin, fake_model):
    parent = _engine(fake_model, [fake_model.text("Hi.")], [fake_model.accept()])
    parent_result = await parent.run(session_id=SESSION_ID, task="Say hi.", principal=admin)

    stranger = Principal(id="other-admin", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)
    child = _engine(fake_model, [], [])

    with pytest.raises(PermissionError):
        await child.spawn_subagent(
            parent_run_id=parent_result["run_id"],
            session_id=SESSION_ID,
            task="Do something.",
            role="research",
            budget=1.0,
            principal=stranger,
        )
