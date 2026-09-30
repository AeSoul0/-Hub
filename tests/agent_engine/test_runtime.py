"""
@file tests/agent_engine/test_runtime.py
@description Security and behavior tests for the native AgentRuntime.

The suite validates explicit Principal propagation, deterministic execution,
tool proposal/run binding, retry behavior, timeout handling, cancellation,
and checker failure semantics without requiring a live LLM or database.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.agent_engine.errors import (
    MaxTurnsReachedError,
    TaskTimeoutError,
)
from app.agent_engine.models import (
    CheckerDecision,
    CheckerDecisionEnum,
    ToolProposal,
    ToolSpec,
)
from app.agent_engine.runtime import AgentRuntime
from app.core.security import Principal, RoleEnum
from app.runtime.tool_gateway import ToolResult


# ==============================================================================
# TEST FIXTURES
# ==============================================================================


@pytest.fixture
def principal() -> Principal:
    """
    Return a stable authenticated Principal for runtime tests.
    """
    return Principal(
        id="user-1",
        role=RoleEnum.USER,
        workspace_id="workspace-1",
    )


@pytest.fixture
def runtime_context(principal: Principal) -> dict:
    """
    Return the trusted runtime identity parameters.
    """
    return {
        "run_id": "run-test-1",
        "session_id": "session-test-1",
        "workspace_id": principal.workspace_id,
        "principal": principal,
    }


@pytest.fixture
def tool_spec() -> ToolSpec:
    """
    Return a minimal safe tool specification.
    """
    return ToolSpec(
        name="my_tool",
        version="1.0.0",
        description="Test tool.",
        input_schema={
            "type": "object",
        },
        output_schema={
            "type": "string",
        },
        risk_level="LOW",
        permissions=[],
        network_access=False,
        filesystem_access=False,
        max_runtime=30,
        max_output=4000,
        max_cost=0.0,
        idempotent=False,
        requires_approval=False,
        sandbox_profile="default",
        audit_policy="standard",
    )


class CancellationToken:
    """
    Minimal cancellation token used by the runtime tests.
    """

    def __init__(self) -> None:
        self.is_cancelled = False

    def cancel(self) -> None:
        self.is_cancelled = True


class MockWorker:
    """
    Deterministic worker returning predefined responses.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.contexts = []

    async def generate(self, context):
        self.contexts.append(dict(context))

        if self.call_count >= len(self.responses):
            raise RuntimeError(
                "No more mocked worker responses."
            )

        response = self.responses[self.call_count]
        self.call_count += 1

        if isinstance(response, Exception):
            raise response

        return response


class MockChecker:
    """
    Deterministic checker returning predefined decisions.
    """

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.call_count = 0
        self.calls = []

    async def evaluate(self, task, result, trace):
        self.calls.append(
            {
                "task": task,
                "result": result,
                "trace": trace,
            }
        )

        if self.call_count >= len(self.decisions):
            raise RuntimeError(
                "No more mocked checker decisions."
            )

        decision = self.decisions[self.call_count]
        self.call_count += 1

        if isinstance(decision, Exception):
            raise decision

        return decision


class MockToolGateway:
    """
    Minimal gateway implementing the current native execute contract.
    """

    def __init__(self, output="tool_success"):
        self.output = output
        self.invocations = []

    async def execute(
        self,
        invocation,
        executor_callback,
        task_context=None,
    ):
        self.invocations.append(
            invocation
        )

        result = await executor_callback(
            **invocation.arguments
        )

        return ToolResult(
            success=True,
            output=result,
        )


# ==============================================================================
# TEST HELPERS
# ==============================================================================


def _patch_runtime_dependencies(
    tool_spec: ToolSpec,
):
    """
    Patch persistence and tool resolution for isolated runtime tests.
    """
    return (
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch.object(
            AgentRuntime,
            "_resolve_tool",
            return_value=(
                lambda **_: "tool_success",
                SimpleNamespace(
                    name=tool_spec.name,
                ),
            ),
        ),
        patch.object(
            AgentRuntime,
            "_build_tool_spec",
            return_value=tool_spec,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    )


# ==============================================================================
# BASIC EXECUTION
# ==============================================================================


def test_task_without_tool(
    runtime_context,
):
    """
    A worker output without tool calls must pass through the checker.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "success",
                "tool_proposals": [],
            }
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        result = asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                **runtime_context,
            )
        )
    finally:
        for item in reversed(patches):
            item.stop()

    assert result == "success"

    assert worker.contexts[0]["run_id"] == "run-test-1"
    assert worker.contexts[0]["session_id"] == "session-test-1"
    assert worker.contexts[0]["workspace_id"] == "workspace-1"
    assert worker.contexts[0]["principal_id"] == "user-1"


# ==============================================================================
# TOOL EXECUTION
# ==============================================================================


def test_task_with_tool(
    runtime_context,
    tool_spec,
):
    """
    Tool execution must use the current ToolGateway invocation contract.
    """
    gateway = MockToolGateway()

    runtime = AgentRuntime(
        tool_gateway=gateway
    )

    worker = MockWorker(
        [
            {
                "tool_proposals": [
                    ToolProposal(
                        tool_call_id="call-1",
                        tool_name="my_tool",
                        arguments={},
                        run_id="run-test-1",
                    )
                ]
            },
            {
                "output": "final result",
                "tool_proposals": [],
            },
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    patches = _patch_runtime_dependencies(
        tool_spec
    )

    for item in patches:
        item.start()

    try:
        result = asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                **runtime_context,
            )
        )
    finally:
        for item in reversed(patches):
            item.stop()

    assert result == "final result"
    assert len(gateway.invocations) == 1
    assert gateway.invocations[0].run_id == "run-test-1"
    assert gateway.invocations[0].principal.id == "user-1"


def test_tool_proposal_run_id_mismatch_is_rejected(
    runtime_context,
    tool_spec,
):
    """
    A worker cannot execute a tool proposal belonging to another run.
    """
    runtime = AgentRuntime(
        tool_gateway=MockToolGateway()
    )

    worker = MockWorker(
        [
            {
                "tool_proposals": [
                    ToolProposal(
                        tool_call_id="call-1",
                        tool_name="my_tool",
                        arguments={},
                        run_id="different-run",
                    )
                ]
            }
        ]
    )

    checker = MockChecker([])

    patches = _patch_runtime_dependencies(
        tool_spec
    )

    for item in patches:
        item.start()

    try:
        with pytest.raises(PermissionError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=worker,
                    checker=checker,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()


# ==============================================================================
# SECURITY CONTEXT VALIDATION
# ==============================================================================


def test_runtime_requires_explicit_principal():
    """
    AgentRuntime must fail closed when authentication context is missing.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "success",
                "tool_proposals": [],
            }
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    with pytest.raises(PermissionError):
        asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                run_id="run-test-1",
                session_id="session-test-1",
                workspace_id="workspace-1",
                principal=None,
            )
        )


def test_runtime_rejects_workspace_mismatch(
    principal,
):
    """
    A Principal cannot execute a run in another workspace.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "success",
                "tool_proposals": [],
            }
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    with pytest.raises(PermissionError):
        asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                run_id="run-test-1",
                session_id="session-test-1",
                workspace_id="other-workspace",
                principal=principal,
            )
        )


# ==============================================================================
# CONTROL FLOW
# ==============================================================================


def test_timeout(
    runtime_context,
):
    """
    Worker timeout must fail the execution deterministically.
    """

    class SlowWorker:
        async def generate(self, context):
            await asyncio.sleep(0.5)
            return {
                "output": "slow",
                "tool_proposals": [],
            }

    runtime = AgentRuntime()

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        with pytest.raises(TaskTimeoutError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=SlowWorker(),
                    checker=checker,
                    timeout=0.1,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()


def test_cancellation(
    runtime_context,
):
    """
    A pre-cancelled execution must stop before worker execution.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "success",
                "tool_proposals": [],
            }
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            )
        ]
    )

    token = CancellationToken()
    token.cancel()

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        result = asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                cancellation_token=token,
                **runtime_context,
            )
        )
    finally:
        for item in reversed(patches):
            item.stop()

    assert result is None
    assert worker.call_count == 0


def test_max_turns(
    runtime_context,
    tool_spec,
):
    """
    Repeated worker tool proposals must respect the turn limit.
    """
    runtime = AgentRuntime(
        tool_gateway=MockToolGateway()
    )

    worker = MockWorker(
        [
            {
                "tool_proposals": [
                    ToolProposal(
                        tool_call_id=f"call-{index}",
                        tool_name="my_tool",
                        arguments={},
                        run_id="run-test-1",
                    )
                ]
            }
            for index in range(4)
        ]
    )

    checker = MockChecker([])

    patches = _patch_runtime_dependencies(
        tool_spec
    )

    for item in patches:
        item.start()

    try:
        with pytest.raises(MaxTurnsReachedError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=worker,
                    checker=checker,
                    max_turns=3,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()


# ==============================================================================
# WORKER / CHECKER FAILURE
# ==============================================================================


def test_model_failure(
    runtime_context,
):
    """
    Worker failures must result in a deterministic runtime failure.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            RuntimeError(
                "LLM crashed"
            )
        ]
    )

    checker = MockChecker([])

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        with pytest.raises(MaxTurnsReachedError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=worker,
                    checker=checker,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()


def test_checker_reject_and_retry(
    runtime_context,
):
    """
    A retry decision must create a fresh attempt with checker feedback.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "bad result",
                "tool_proposals": [],
            },
            {
                "output": "good result",
                "tool_proposals": [],
            },
        ]
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.RETRY,
                retry_instruction="fix it",
            ),
            CheckerDecision(
                status=CheckerDecisionEnum.ACCEPT
            ),
        ]
    )

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        result = asyncio.run(
            runtime.execute_task(
                task={
                    "description": "test",
                },
                orchestrator=None,
                worker=worker,
                checker=checker,
                **runtime_context,
            )
        )
    finally:
        for item in reversed(patches):
            item.stop()

    assert result == "good result"
    assert worker.contexts[1]["feedback"] == "fix it"


def test_max_attempts(
    runtime_context,
):
    """
    Repeated checker retries must stop at the configured attempt limit.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "bad result",
                "tool_proposals": [],
            }
        ]
        * 3
    )

    checker = MockChecker(
        [
            CheckerDecision(
                status=CheckerDecisionEnum.RETRY,
                retry_instruction="fix it",
            )
        ]
        * 3
    )

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        with pytest.raises(MaxTurnsReachedError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=worker,
                    checker=checker,
                    max_attempts=2,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()


def test_checker_failure(
    runtime_context,
):
    """
    A checker exception must fail closed as an execution failure.
    """
    runtime = AgentRuntime()

    worker = MockWorker(
        [
            {
                "output": "success",
                "tool_proposals": [],
            }
        ]
    )

    checker = MockChecker(
        [
            RuntimeError(
                "Checker crashed"
            )
        ]
    )

    patches = [
        patch(
            "app.agent_engine.runtime.AgentStateManager.load_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.AgentStateManager.save_agent_run",
            return_value=None,
        ),
        patch(
            "app.agent_engine.runtime.EventDispatcher.dispatch",
            return_value=None,
        ),
    ]

    for item in patches:
        item.start()

    try:
        with pytest.raises(MaxTurnsReachedError):
            asyncio.run(
                runtime.execute_task(
                    task={
                        "description": "test",
                    },
                    orchestrator=None,
                    worker=worker,
                    checker=checker,
                    **runtime_context,
                )
            )
    finally:
        for item in reversed(patches):
            item.stop()