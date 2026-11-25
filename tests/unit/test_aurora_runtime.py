"""
@file tests/unit/test_aurora_runtime.py
@description Unit tests for the native Aurora compatibility facade.

These tests verify that the historical ainvoke contract is implemented
through the native AgentRuntime while preserving the authenticated
Principal and workspace boundary.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import Principal, RoleEnum
from app.runtime.aurora import (
    NativeAuroraApplication,
    run_aurora_agent,
)


# ==============================================================================
# TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_aurora_ainvoke_uses_native_runtime() -> None:
    """Aurora must delegate execution to the native AgentRuntime."""
    app = NativeAuroraApplication()

    app.runtime.execute_task = AsyncMock(
        return_value="native result",
    )

    principal = Principal(
        id="user-1",
        role=RoleEnum.USER,
        workspace_id="workspace-1",
    )

    result = await app.ainvoke(
        {
            "messages": [
                SimpleNamespace(
                    content="hello",
                ),
            ],
            "session_id": "session-1",
            "current_intent": "hello",
            "principal": principal,
        },
    )

    assert result["session_id"] == "session-1"
    assert result["principal"] is principal
    assert result["messages"][0].content == "native result"

    app.runtime.execute_task.assert_awaited_once()

    runtime_kwargs = (
        app.runtime.execute_task.await_args.kwargs
    )

    assert runtime_kwargs["principal"] is principal
    assert (
        runtime_kwargs["workspace_id"]
        == "workspace-1"
    )
    assert (
        runtime_kwargs["session_id"]
        == "session-1"
    )


@pytest.mark.asyncio
async def test_aurora_rejects_missing_principal() -> None:
    """
    Direct Aurora invocation without an explicit Principal must fail closed.
    """
    app = NativeAuroraApplication()

    with pytest.raises(
        ValueError,
        match="valid Principal",
    ):
        await app.ainvoke(
            {
                "messages": [
                    {
                        "content": "hello",
                    },
                ],
                "session_id": "session-1",
                "current_intent": "hello",
            },
        )


@pytest.mark.asyncio
async def test_aurora_rejects_invalid_principal() -> None:
    """Reject malformed principal objects before runtime execution."""
    app = NativeAuroraApplication()

    with pytest.raises(
        ValueError,
        match="valid Principal",
    ):
        await app.ainvoke(
            {
                "messages": [
                    {
                        "content": "hello",
                    },
                ],
                "session_id": "session-1",
                "current_intent": "hello",
                "principal": "invalid",
            },
        )


@pytest.mark.asyncio
async def test_aurora_rejects_missing_workspace() -> None:
    """Reject principals without a tenant/workspace binding."""
    app = NativeAuroraApplication()

    principal = Principal(
        id="user-1",
        role=RoleEnum.USER,
        workspace_id="",
    )

    with pytest.raises(
        ValueError,
        match="principal workspace",
    ):
        await app.ainvoke(
            {
                "messages": [
                    {
                        "content": "hello",
                    },
                ],
                "session_id": "session-1",
                "current_intent": "hello",
                "principal": principal,
            },
        )


@pytest.mark.asyncio
async def test_aurora_legacy_message_shape_is_supported() -> None:
    """Existing callers using message dictionaries remain compatible."""
    app = NativeAuroraApplication()

    app.runtime.execute_task = AsyncMock(
        return_value="ok",
    )

    principal = Principal(
        id="user-1",
        role=RoleEnum.USER,
        workspace_id="workspace-1",
    )

    result = await app.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "test request",
                },
            ],
            "session_id": "session-1",
            "principal": principal,
        },
    )

    assert result["messages"][0].content == "ok"

    runtime_kwargs = (
        app.runtime.execute_task.await_args.kwargs
    )

    assert (
        runtime_kwargs["principal"]
        is principal
    )


@pytest.mark.asyncio
async def test_run_aurora_agent_preserves_principal_boundary() -> None:
    """
    The public voice/runtime helper must preserve the authenticated Principal.
    """
    principal = Principal(
        id="user-2",
        role=RoleEnum.MEMBER,
        workspace_id="workspace-9",
    )

    with patch(
        "app.runtime.aurora.get_aurora_app",
    ) as get_app:
        app = AsyncMock()

        app.ainvoke.return_value = {
            "messages": [
                SimpleNamespace(
                    content="response",
                ),
            ],
            "session_id": "voice-session",
            "principal": principal,
        }

        get_app.return_value = app

        result = await run_aurora_agent(
            session_id="voice-session",
            transcript="test",
            principal=principal,
        )

    assert result["principal"] is principal

    app.ainvoke.assert_awaited_once()

    invocation = (
        app.ainvoke.await_args.args[0]
    )

    assert (
        invocation["principal"]
        is principal
    )
    assert (
        invocation["session_id"]
        == "voice-session"
    )