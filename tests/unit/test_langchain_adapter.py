"""
@file tests/unit/test_langchain_adapter.py
@description Unit tests for the framework-agnostic legacy model adapter.

The tests ensure that the historical LangchainModelAdapter name remains
compatible while enforcing the native ModelProvider contract and explicit
runtime run identity.
"""

import pytest

from app.agent_engine.adapters.langchain_adapter import (
    LangchainModelAdapter,
)
from app.agent_engine.models import ToolProposal


# ==============================================================================
# MOCK MODEL
# ==============================================================================


class MockModel:
    """
    Minimal native async model implementation.
    """

    model_name = "mock-model"

    def __init__(
        self,
        response,
    ):
        self.response = response
        self.payload = None

    async def ainvoke(
        self,
        payload,
    ):
        self.payload = payload
        return self.response


# ==============================================================================
# GENERATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_adapter_generates_native_output():
    """
    Plain model output must be normalized to the native runtime contract.
    """
    model = MockModel(
        {
            "output": "hello",
            "tool_calls": [],
        }
    )

    adapter = LangchainModelAdapter(
        model
    )

    result = await adapter.generate(
        {
            "run_id": "run-1",
            "session_id": "session-1",
            "workspace_id": "workspace-1",
            "principal_id": "user-1",
            "task": {
                "description": "Say hello",
            },
        }
    )

    assert result["output"] == "hello"
    assert result["tool_proposals"] == []

    assert model.payload["run_id"] == "run-1"
    assert model.payload["session_id"] == "session-1"
    assert model.payload["workspace_id"] == "workspace-1"
    assert model.payload["principal_id"] == "user-1"


@pytest.mark.asyncio
async def test_adapter_normalizes_tool_calls():
    """
    Native model tool-call responses must become ToolProposal instances.
    """
    model = MockModel(
        {
            "output": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "save_memory",
                    "arguments": {
                        "fact": "User prefers concise answers.",
                    },
                }
            ],
        }
    )

    adapter = LangchainModelAdapter(
        model
    )

    result = await adapter.generate(
        {
            "run_id": "run-42",
            "task": {
                "description": "Remember this preference.",
            },
        }
    )

    assert len(
        result["tool_proposals"]
    ) == 1

    proposal = result[
        "tool_proposals"
    ][0]

    assert isinstance(
        proposal,
        ToolProposal,
    )

    assert proposal.tool_call_id == "call-1"
    assert proposal.tool_name == "save_memory"
    assert proposal.arguments == {
        "fact": "User prefers concise answers.",
    }
    assert proposal.run_id == "run-42"


@pytest.mark.asyncio
async def test_adapter_requires_run_id_for_tool_proposals():
    """
    Tool proposals without an explicit trusted run ID must fail closed.
    """
    model = MockModel(
        {
            "output": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "save_memory",
                    "arguments": {
                        "fact": "test",
                    },
                }
            ],
        }
    )

    adapter = LangchainModelAdapter(
        model
    )

    with pytest.raises(
        ValueError,
        match="run_id",
    ):
        await adapter.generate(
            {
                "task": {
                    "description": "test",
                },
            }
        )


@pytest.mark.asyncio
async def test_adapter_rejects_model_without_ainvoke():
    """
    The compatibility adapter must require the native async model contract.
    """
    class InvalidModel:
        pass

    adapter = LangchainModelAdapter(
        InvalidModel()
    )

    with pytest.raises(
        TypeError,
        match="ainvoke",
    ):
        await adapter.generate(
            {
                "run_id": "run-1",
                "task": {
                    "description": "test",
                },
            }
        )