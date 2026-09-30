"""
@file tests/unit/test_openai_adapter.py
@description Unit tests for the native OpenAI Responses API adapter.

The suite verifies request normalization, system instructions, registered
function tools, plain model output, and conversion of Responses API function
calls into native ToolProposal objects without making real network requests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_engine.adapters.openai_adapter import OpenAIAdapter


def make_context() -> dict:
    """
    Build a deterministic native runtime context for adapter tests.
    """
    return {
        "run_id": "run-test",
        "task": {
            "description": "Execute the requested test operation."
        },
        "feedback": "Use the registered tool when required.",
        "observations": [],
        "system_prompt": "You are a secure test agent.",
        "tools": [
            {
                "type": "function",
                "name": "test_tool",
                "description": "A deterministic test tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {
                            "type": "string"
                        }
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_generate_returns_plain_model_output() -> None:
    """
    Verify a normal Responses API message is normalized correctly.
    """
    response = SimpleNamespace(
        id="resp-1",
        output_text="Execution completed successfully.",
        output=[],
    )

    client = MagicMock()
    client.responses.create = AsyncMock(
        return_value=response
    )

    adapter = OpenAIAdapter(
        model_name="test-model",
        api_key="test-key",
    )

    with patch.object(
        adapter,
        "_client",
        client,
    ):
        result = await adapter.generate(
            make_context()
        )

    assert result["output"] == (
        "Execution completed successfully."
    )

    assert result["tool_proposals"] == []

    client.responses.create.assert_awaited_once()

    request = client.responses.create.await_args.kwargs

    assert request["model"] == "test-model"
    assert request["instructions"] == (
        "You are a secure test agent."
    )

    assert request["input"][0] == {
        "role": "user",
        "content": "Execute the requested test operation.",
    }

    assert request["input"][1] == {
        "role": "user",
        "content": (
            "Checker feedback:\n"
            "Use the registered tool when required."
        ),
    }

    assert request["tools"][0]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_generate_converts_function_call_to_tool_proposal() -> None:
    """
    Verify a Responses API function_call becomes a native ToolProposal.
    """
    function_call = SimpleNamespace(
        type="function_call",
        name="test_tool",
        call_id="call-123",
        arguments='{"value":"hello"}',
    )

    response = SimpleNamespace(
        id="resp-tool-1",
        output_text="",
        output=[
            function_call
        ],
    )

    client = MagicMock()
    client.responses.create = AsyncMock(
        return_value=response
    )

    adapter = OpenAIAdapter(
        model_name="test-model",
        api_key="test-key",
    )

    with patch.object(
        adapter,
        "_client",
        client,
    ):
        result = await adapter.generate(
            make_context()
        )

    assert len(
        result["tool_proposals"]
    ) == 1

    proposal = result["tool_proposals"][0]

    assert proposal.tool_call_id == "call-123"
    assert proposal.tool_name == "test_tool"
    assert proposal.arguments == {
        "value": "hello"
    }
    assert proposal.run_id == "run-test"


@pytest.mark.asyncio
async def test_generate_rejects_invalid_function_arguments() -> None:
    """
    Invalid function-call JSON must fail instead of reaching ToolGateway.
    """
    function_call = SimpleNamespace(
        type="function_call",
        name="test_tool",
        call_id="call-invalid",
        arguments="{invalid-json",
    )

    response = SimpleNamespace(
        id="resp-invalid",
        output_text="",
        output=[
            function_call
        ],
    )

    client = MagicMock()
    client.responses.create = AsyncMock(
        return_value=response
    )

    adapter = OpenAIAdapter(
        model_name="test-model",
        api_key="test-key",
    )

    with patch.object(
        adapter,
        "_client",
        client,
    ):
        with pytest.raises(
            ValueError,
            match="Invalid JSON arguments",
        ):
            await adapter.generate(
                make_context()
            )


def test_adapter_requires_api_key() -> None:
    """
    The adapter must not silently construct an unauthenticated client.
    """
    adapter = OpenAIAdapter(
        model_name="test-model",
        api_key=None,
    )

    with patch(
        "app.agent_engine.adapters.openai_adapter.os.getenv",
        return_value=None,
    ):
        with pytest.raises(
            RuntimeError,
            match="OPENAI_API_KEY",
        ):
            adapter._get_client()