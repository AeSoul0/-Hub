"""
@file tests/agent_engine/test_streaming.py
@description N1 (ADR-040): the draft of an answer while the model writes it.

- with a draft open the adapter streams: the text so far goes out as
  answer.delta, the result is the same as without streaming;
- a turn that calls a tool was not the answer: the draft is reset;
- a provider that cannot stream is asked again without it;
- the Critic and subagents never write into the draft; a rejected answer
  resets it;
- "live" delivery: the reply carries no audio and says the Nucleo speaks it
  sentence by sentence; a sentence of a reply too long for the cloud is
  spoken by Piper.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.agent_engine import streaming
from app.agent_engine.adapters.pydantic_ai_adapter import PydanticAIAdapter
from app.agent_engine.checker import AgentChecker
from app.agent_engine.streaming import DraftStream, current_draft, streaming_answer
from app.agents import orchestrator
from app.core.security import Principal, RoleEnum
from app.voice import pipeline

OWNER = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-n1")


@pytest.fixture
def published(monkeypatch) -> List[tuple]:
    events: List[tuple] = []

    async def publish(session_id: str, event_type: str, data: Any, workspace_id: str = "") -> None:
        events.append((event_type, data, workspace_id))

    monkeypatch.setattr("app.core.event_bus.event_bus.publish", publish)
    # Every piece on the wire, so the test sees each step.
    monkeypatch.setattr(streaming, "DRAFT_INTERVAL", 0.0)
    return events


def adapter_with(model: FunctionModel) -> PydanticAIAdapter:
    adapter = PydanticAIAdapter(model_name="fake", provider="openai", api_key="test-only")
    adapter._model = model
    adapter._model_client = adapter._client
    return adapter


async def words(messages: Any, info: AgentInfo) -> AsyncIterator[str]:
    for piece in ("La luce ", "della cucina ", "è accesa."):
        yield piece


async def tool_then_nothing(messages: Any, info: AgentInfo) -> AsyncIterator[Any]:
    yield "Controllo "
    yield {0: DeltaToolCall(name="list_folder", json_args='{"path": "."}', tool_call_id="call-1")}


async def test_the_draft_follows_the_model_and_the_result_is_the_same(published):
    adapter = adapter_with(FunctionModel(stream_function=words))

    with streaming_answer(DraftStream("s", "workspace-n1")):
        result = await adapter.generate({"prompt": "accendi", "run_id": "run-1"})

    assert result["output"] == "La luce della cucina è accesa."
    assert result["tool_proposals"] == []
    drafts = [data["text"] for kind, data, _ in published if kind == "answer.delta"]
    assert drafts == ["La luce ", "La luce della cucina ", "La luce della cucina è accesa."]
    assert all(workspace == "workspace-n1" for _, _, workspace in published)


async def test_without_a_draft_nothing_is_published(published):
    adapter = adapter_with(FunctionModel(stream_function=words))
    with pytest.raises(Exception):
        # Not streamed: this stand-in model can only stream, so the plain request fails.
        await adapter.generate({"prompt": "accendi"})
    assert published == []


async def test_a_turn_with_a_tool_call_resets_the_draft(published):
    adapter = adapter_with(FunctionModel(stream_function=tool_then_nothing))

    with streaming_answer(DraftStream("s", "workspace-n1")):
        result = await adapter.generate(
            {
                "prompt": "cosa c'è?",
                "run_id": "run-2",
                "tools": [{"name": "list_folder", "description": "x", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}],
            }
        )

    assert [proposal.tool_name for proposal in result["tool_proposals"]] == ["list_folder"]
    assert [kind for kind, _, _ in published] == ["answer.delta", "answer.reset"]


async def test_a_provider_that_cannot_stream_answers_anyway(published):
    def whole(messages: Any, info: AgentInfo) -> Any:
        from pydantic_ai.messages import ModelResponse, TextPart

        return ModelResponse(parts=[TextPart("Fatto.")])

    adapter = adapter_with(FunctionModel(whole))

    with streaming_answer(DraftStream("s", "workspace-n1")):
        result = await adapter.generate({"prompt": "x"})

    assert result["output"] == "Fatto."
    assert published == []


async def test_the_critic_and_subagents_do_not_write_the_draft():
    seen: List[Any] = []

    class Recorder:
        model_name = "critic"

        async def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
            seen.append(current_draft())
            return {"output": '{"status": "ACCEPT"}'}

    with streaming_answer(DraftStream("s", "w")):
        await AgentChecker(Recorder()).evaluate(task={"description": "x"}, result="y", trace=[])

    assert seen == [None]

    # The subagent path wraps execute_task the same way (runtime_subagents.py).
    import inspect

    from app.agent_engine import runtime_subagents

    assert "with streaming_answer(None):" in inspect.getsource(runtime_subagents)


async def test_live_delivery_leaves_the_voice_to_the_nucleo(monkeypatch, published):
    spoken = AsyncMock(return_value=("QUJD", "audio/wav"))
    monkeypatch.setattr(orchestrator, "speak", spoken)

    class Engine:
        async def ainvoke(self, state: Dict[str, Any], config: Any = None) -> Dict[str, Any]:
            assert current_draft() is not None
            return {"messages": [{"content": "La luce è accesa."}]}

    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=Engine()))
    monkeypatch.setattr(orchestrator, "_decision_reply", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_instant_reply", AsyncMock(return_value=None))

    live = await orchestrator.generate_ai_response("accendi la luce", "", "", "s", principal=OWNER, delivery="live")
    assert live == {"transcription": "La luce è accesa.", "audio_base64": "", "audio_mime": "", "speak": "sentences"}
    spoken.assert_not_called()
    # The answer also goes on the workspace channel, for a request cut by a proxy.
    assert [event for event in published if event[0] == "answer.final"][-1] == (
        "answer.final",
        {"reply": {"transcription": "La luce è accesa.", "speak": "sentences"}},
        "workspace-n1",
    )
    published.clear()

    class Plain(Engine):
        async def ainvoke(self, state: Dict[str, Any], config: Any = None) -> Dict[str, Any]:
            assert current_draft() is None
            return {"messages": [{"content": "La luce è accesa."}]}

    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=Plain()))
    full = await orchestrator.generate_ai_response("accendi la luce", "", "", "s", principal=OWNER)
    assert full["audio_base64"] == "QUJD" and "speak" not in full
    assert [event for event in published if event[0].startswith("answer.")] == []

    # A live command that fails says so on the channel too.
    class Broken(Engine):
        async def ainvoke(self, state: Dict[str, Any], config: Any = None) -> Dict[str, Any]:
            raise RuntimeError("no provider")

    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=Broken()))
    with pytest.raises(RuntimeError):
        await orchestrator.generate_ai_response("x", "", "", "s", principal=OWNER, delivery="live")
    assert [event for event in published if event[0].startswith("answer.")] == [
        ("answer.failed", {"detail": "no provider"}, "workspace-n1")
    ]

    with pytest.raises(ValueError):
        await orchestrator.generate_ai_response("x", "", "", "s", principal=OWNER, delivery="odd")


async def test_a_sentence_of_a_long_reply_is_spoken_by_piper(monkeypatch):
    class Local:
        def synthesize(self, text: str):
            return b"local", "audio/wav"

    class Cloud:
        fallback = Local()

        def synthesize(self, text: str):
            return b"cloud", "audio/mpeg"

    monkeypatch.setattr(pipeline, "text_to_speech", lambda: Cloud())

    assert await pipeline.speak("Prima frase.") == ("Y2xvdWQ=", "audio/mpeg")
    assert await pipeline.speak("Prima frase.", local=True) == ("bG9jYWw=", "audio/wav")


async def test_a_stopped_run_is_one_line_not_its_state(monkeypatch, published):
    """The run's raw state ({'status': 'CANCELLED', ...}) is never the answer."""
    from app.core import interface

    monkeypatch.setattr(interface, "interface_language", lambda: "it")
    monkeypatch.setattr(orchestrator, "_decision_reply", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_instant_reply", AsyncMock(return_value=None))
    states = {
        "Comando fermato dallo stop generale.": {
            "status": "CANCELLED",
            "run_id": "r",
            "reason": "Stopped by the global kill switch (owner).",
            "usage": {"model_calls": None},
        },
        "Comando fermato.": {"status": "CANCELLED", "run_id": "r", "reason": "Cancelled by owner."},
        "Comando fermato: budget raggiunto (monthly budget).": {
            "status": "BUDGET_EXCEEDED",
            "run_id": "r",
            "reason": "monthly budget",
        },
    }
    for line, state in states.items():

        class Stopped:
            async def ainvoke(self, _state: Dict[str, Any], config: Any = None, state=state) -> Dict[str, Any]:
                return {"messages": [{"content": state}]}

        monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=Stopped()))
        reply = await orchestrator.generate_ai_response("x", "", "", "s", principal=OWNER, delivery="live")
        assert reply["stopped"] == line
        assert reply["transcription"] == ""


async def test_commands_running_together_are_told_apart(monkeypatch, published):
    """The page's command id goes with the drafts and the end of its command."""
    monkeypatch.setattr(orchestrator, "_decision_reply", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_instant_reply", AsyncMock(return_value=None))

    class Engine:
        async def ainvoke(self, state: Dict[str, Any], config: Any = None) -> Dict[str, Any]:
            draft = current_draft()
            await draft.delta("Ciao")
            await draft.flush()
            return {"messages": [{"content": "Ciao!"}]}

    monkeypatch.setattr(orchestrator, "get_aurora_app", AsyncMock(return_value=Engine()))
    await orchestrator.generate_ai_response(
        "ciao", "", "", "s", principal=OWNER, delivery="live", command_id="c-1", input_channel="voice"
    )
    answers = [(kind, data) for kind, data, _ in published if kind.startswith("answer.")]
    assert answers[0] == ("answer.delta", {"text": "Ciao", "command_id": "c-1"})
    assert answers[-1][1]["command_id"] == "c-1"
    # A voice command says what was heard, for a request that was cut.
    assert answers[-1][1]["heard"] == "ciao"

    # Anything that is not an id is dropped.
    published.clear()
    await orchestrator.generate_ai_response("ciao", "", "", "s", principal=OWNER, delivery="live", command_id="<x>")
    assert all("command_id" not in data for kind, data, _ in published if kind.startswith("answer."))
