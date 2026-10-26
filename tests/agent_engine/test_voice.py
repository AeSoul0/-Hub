"""
@file tests/agent_engine/test_voice.py
@description M15 (ADR-021): the local voice path and the voice rule.

- engines: off by AEHUB_VOICE, replaceable, missing packages reported;
- pipeline: transcript, size limit, speech is best effort;
- policy: a HIGH action asked by voice always waits for approval, even for
  the ADMIN in a clean run; the same call typed goes through;
- end to end through AgentEngine -> AgentRuntime -> ToolGateway, for the
  run and for a voice run's subagent;
- /api/orchestrator/listen: transcript in, run marked as voice.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_engine.application import AgentEngine
from app.agent_engine.runtime import AgentRuntime
from app.api import approvals as approvals_api
from app.api.realtime import decode_audio_payload
from app.core.security import (
    BudgetState,
    PolicyEngine,
    Principal,
    RoleEnum,
    TaskExecutionContext,
    ToolProposal,
    WorkspacePolicy,
)
from app.domain.models.audit import ApprovalRecord
from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata
from app.voice import engines
from app.voice.pipeline import MAX_AUDIO_BYTES, AudioTooLarge, speak, transcribe_audio


SESSION_ID = "session-voice"
WORKSPACE_ID = "workspace-voice"


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.heard: List[bytes] = []

    def transcribe(self, audio: bytes) -> str:
        self.heard.append(audio)
        return self.text


class FakeTTS:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.spoken: List[str] = []

    def synthesize(self, text: str) -> Tuple[bytes, str]:
        if self.fail:
            raise RuntimeError("model file is corrupt")
        self.spoken.append(text)
        return b"RIFF-fake-wav", "audio/wav"


@pytest.fixture
def voice_on(monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE", "local")
    yield
    engines.set_engines()


def _schema(**properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class HouseSkill(BaseSkill):
    """
    A LOW and a HIGH action, both without requires_approval: only the voice
    rule can stop the HIGH one in a clean run.
    """

    def __init__(self) -> None:
        self.executed: List[str] = []

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(name="house_lab", description="Voice test lab.")

    @property
    def tools(self):
        def turn_on_light(room: str) -> str:
            self.executed.append("turn_on_light")
            return f"light on in {room}"

        def open_garage(confirm: bool) -> str:
            self.executed.append("open_garage")
            return "garage open"

        return [turn_on_light, open_garage]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "turn_on_light": ToolMetadata(
                name="turn_on_light",
                description="Turn on a light.",
                risk_level=RiskLevel.LOW,
                input_schema=_schema(room={"type": "string"}),
            ),
            "open_garage": ToolMetadata(
                name="open_garage",
                description="Open the garage door.",
                risk_level=RiskLevel.HIGH,
                requires_approval=False,
                input_schema=_schema(confirm={"type": "boolean"}),
            ),
        }


@pytest.fixture
def house(agent_infrastructure) -> HouseSkill:
    skill = HouseSkill()
    agent_infrastructure.use_skills(skill)
    return skill


@pytest.fixture
def admin() -> Principal:
    return Principal(id="owner", role=RoleEnum.ADMIN, workspace_id=WORKSPACE_ID)


def _engine(fake_model, script: List[Any]) -> AgentEngine:
    return AgentEngine(
        model_provider=fake_model.adapter(script),
        checker_provider=fake_model.checker([fake_model.accept(), fake_model.accept()]),
        runtime=AgentRuntime(),
    )


# ==============================================================================
# ENGINES AND PIPELINE
# ==============================================================================


def test_voice_off_means_no_engine(monkeypatch):
    monkeypatch.setenv("AEHUB_VOICE", "off")

    with pytest.raises(engines.VoiceUnavailable, match="off"):
        engines.speech_to_text()


def test_missing_packages_are_named(voice_on, monkeypatch):
    monkeypatch.setattr(engines.importlib.util, "find_spec", lambda name: None)
    engines.set_engines()

    with pytest.raises(engines.VoiceUnavailable, match="faster-whisper, piper-tts"):
        engines.text_to_speech()


async def test_transcript_and_size_limit(voice_on):
    stt = FakeSTT("accendi la luce")
    engines.set_engines(stt=stt, tts=FakeTTS())

    assert await transcribe_audio(b"webm-bytes") == "accendi la luce"
    assert stt.heard == [b"webm-bytes"]
    assert await transcribe_audio(b"") == ""

    with pytest.raises(AudioTooLarge):
        await transcribe_audio(b"x" * (MAX_AUDIO_BYTES + 1))


async def test_speech_is_best_effort(voice_on, monkeypatch):
    tts = FakeTTS()
    engines.set_engines(stt=FakeSTT(""), tts=tts)

    audio, mime = await speak("Luce accesa.")
    assert base64.b64decode(audio) == b"RIFF-fake-wav" and mime == "audio/wav"
    assert tts.spoken == ["Luce accesa."]

    engines.set_engines(stt=FakeSTT(""), tts=FakeTTS(fail=True))
    assert await speak("Luce accesa.") == ("", "")

    monkeypatch.setenv("AEHUB_VOICE", "off")
    assert await speak("Luce accesa.") == ("", "")


def test_websocket_audio_payload():
    raw = b"\x1aE\xdf\xa3webm"
    encoded = base64.b64encode(raw).decode()

    assert decode_audio_payload(encoded) == raw
    assert decode_audio_payload(f"data:audio/webm;base64,{encoded}") == raw

    with pytest.raises(ValueError):
        decode_audio_payload("not base64 !!")


# ==============================================================================
# POLICY
# ==============================================================================


def _decide(admin: Principal, risk: str, channel: str, untrusted: bool = False) -> str:
    spec = SimpleNamespace(
        name="tool",
        risk_level=risk,
        max_cost=0.0,
        permissions=[],
        network_access=False,
        filesystem_access=False,
        requires_approval=False,
    )
    decision = PolicyEngine.authorize_tool(
        principal=admin,
        tool_spec=spec,
        tool_proposal=ToolProposal(tool_call_id="c1", tool_name="tool", arguments={}, run_id="r1"),
        workspace_policy=WorkspacePolicy(),
        budget_state=BudgetState(),
        task_context=TaskExecutionContext(input_channel=channel, untrusted_context=untrusted),
    )
    return getattr(decision.decision, "value", decision.decision)


@pytest.mark.parametrize(
    "risk,channel,expected",
    [
        ("HIGH", "voice", "REQUIRE_APPROVAL"),
        ("HIGH", "text", "ALLOW"),
        ("LOW", "voice", "ALLOW"),
        ("MEDIUM", "voice", "ALLOW"),
    ],
)
def test_voice_rule(admin, risk, channel, expected):
    assert _decide(admin, risk, channel) == expected


# ==============================================================================
# END TO END
# ==============================================================================


async def test_high_action_asked_by_voice_waits_for_approval(
    house, admin, fake_model, db_session_factory, agent_infrastructure
):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "open_garage", {"confirm": True}),
            fake_model.text("Fatto."),
        ],
    )

    await engine.run(
        session_id=SESSION_ID,
        task="Apri il garage.",
        principal=admin,
        input_channel="voice",
    )

    assert house.executed == []

    with db_session_factory() as db:
        approval = db.query(ApprovalRecord).filter(ApprovalRecord.tool == "open_garage").one()
        assert approval.decision is None
        approval_id = approval.id

    # F3: once allowed, the resumed run says it was asked by voice, so the
    # Nucleo speaks its answer.
    with patch.object(approvals_api, "_schedule_resume"):
        decided = await approvals_api.decide_approval(
            approval_id,
            approvals_api.ApprovalDecision(decision="allow"),
            principal=admin,
        )

    with patch.object(approvals_api, "get_agent_engine", return_value=engine):
        await approvals_api.resume_after_decision(decided)

    assert house.executed == ["open_garage"]
    resumed = [data for _, kind, data in agent_infrastructure.published if kind == "run.resumed"]
    assert len(resumed) == 1 and resumed[0]["input_channel"] == "voice"


async def test_same_high_action_typed_goes_through(house, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "open_garage", {"confirm": True}),
            fake_model.text("Fatto."),
        ],
    )

    await engine.run(session_id=SESSION_ID, task="Apri il garage.", principal=admin)

    assert house.executed == ["open_garage"]


async def test_low_action_asked_by_voice_runs(house, admin, fake_model):
    engine = _engine(
        fake_model,
        [
            fake_model.function_call("call_1", "turn_on_light", {"room": "soggiorno"}),
            fake_model.text("Luce accesa."),
        ],
    )

    result = await engine.run(
        session_id=SESSION_ID,
        task="Accendi la luce del soggiorno.",
        principal=admin,
        input_channel="voice",
    )

    assert house.executed == ["turn_on_light"]
    assert result["messages"][0].content == "Luce accesa."


def test_voice_run_marks_its_subagents():
    worker_context = {"task": {"description": "x", "input_channel": "voice"}}

    assert AgentRuntime._input_channel(worker_context) == "voice"
    assert AgentRuntime._input_channel({"task": {"description": "x"}}) == "text"
    # Anything but "voice" is a typed task.
    assert AgentRuntime._input_channel({"task": {"input_channel": "VOICE!"}}) == "text"


# ==============================================================================
# HTTP
# ==============================================================================


def _listen_client(captured: List[Dict[str, Any]], admin: Principal) -> TestClient:
    from app.agents import orchestrator

    async def fake_response(intent, system_prompt, ui_context, session_id, principal=None, input_channel="text"):
        captured.append({"intent": intent, "channel": input_channel, "principal": principal})
        return {"transcription": "Luce accesa.", "audio_base64": "", "audio_mime": ""}

    app = FastAPI()
    app.include_router(orchestrator.router)

    patches = [
        patch("app.agents.orchestrator.generate_ai_response", fake_response),
        patch("app.core.security.resolve_principal", lambda request, db: admin),
        patch("app.core.db.SessionLocal", lambda: _NullSession()),
    ]
    for item in patches:
        item.start()
    client = TestClient(app)
    client.patches = patches  # type: ignore[attr-defined]
    return client


class _NullSession:
    def __enter__(self) -> "_NullSession":
        return self

    def __exit__(self, *exc: Optional[Any]) -> None:
        return None


def _close(client: TestClient) -> None:
    for item in client.patches:  # type: ignore[attr-defined]
        item.stop()


def test_listen_runs_the_transcript_as_voice(voice_on, admin):
    engines.set_engines(stt=FakeSTT("accendi la luce del soggiorno"), tts=FakeTTS())
    captured: List[Dict[str, Any]] = []
    client = _listen_client(captured, admin)

    try:
        response = client.post("/api/orchestrator/listen", files={"file": ("a.webm", b"audio", "audio/webm")})
    finally:
        _close(client)

    assert response.status_code == 200
    assert response.json()["heard"] == "accendi la luce del soggiorno"
    assert captured == [{"intent": "accendi la luce del soggiorno", "channel": "voice", "principal": admin}]


def test_listen_says_when_voice_is_off(monkeypatch, admin):
    monkeypatch.setenv("AEHUB_VOICE", "off")
    captured: List[Dict[str, Any]] = []
    client = _listen_client(captured, admin)

    try:
        response = client.post("/api/orchestrator/listen", files={"file": ("a.webm", b"audio", "audio/webm")})
    finally:
        _close(client)

    assert response.status_code == 503
    assert captured == []


def test_silence_starts_no_run(voice_on, admin):
    engines.set_engines(stt=FakeSTT(""), tts=FakeTTS())
    captured: List[Dict[str, Any]] = []
    client = _listen_client(captured, admin)

    try:
        response = client.post("/api/orchestrator/listen", files={"file": ("a.webm", b"audio", "audio/webm")})
    finally:
        _close(client)

    assert response.status_code == 200 and response.json()["heard"] == ""
    assert captured == []


def test_espeak_data_gets_an_ascii_path(tmp_path, monkeypatch):
    # Piper's espeak-ng cannot open C:\Users\Renée\... or C:\ÆHub\...
    source = tmp_path / "Renée" / "espeak-ng-data"
    source.mkdir(parents=True)
    (source / "phontab").write_bytes(b"data")
    monkeypatch.setenv("AEHUB_VOICE_MODELS_DIR", str(tmp_path / "models"))

    resolved = engines._ascii_path(source)

    assert str(resolved).isascii()
    assert (resolved / "phontab").read_bytes() == b"data"
    assert engines._ascii_path(tmp_path) == tmp_path
