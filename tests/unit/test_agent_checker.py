"""
@file tests/unit/test_agent_checker.py
@description Unit tests for the independent Agent Checker.

The suite verifies the fail-closed security contract of AgentChecker and
ensures valid provider responses are converted into deterministic decisions.
"""

import pytest

from app.agent_engine.checker import AgentChecker
from app.agent_engine.models import CheckerDecisionEnum


class StubModelProvider:
    """
    Minimal async provider used to isolate Checker behavior.
    """

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.last_context = None

    async def generate(self, context):
        self.last_context = context

        if self.error is not None:
            raise self.error

        return self.response


@pytest.mark.asyncio
async def test_checker_accepts_valid_response():
    """
    A valid ACCEPT response must be preserved.
    """
    provider = StubModelProvider(
        response={
            "output": (
                '{"decision":"ACCEPT",'
                '"issues":[]}'
            )
        }
    )

    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "Return a valid answer"},
        result={"answer": "valid"},
        trace=[],
    )

    assert decision.status is CheckerDecisionEnum.ACCEPT
    assert decision.issues == []
    assert provider.last_context is not None


@pytest.mark.asyncio
async def test_checker_returns_retry_for_valid_retry_response():
    """
    A valid RETRY response must preserve issues and instructions.
    """
    provider = StubModelProvider(
        response={
            "output": (
                '{"decision":"RETRY",'
                '"issues":[{"code":"MISSING_INFO","severity":"HIGH"}],'
                '"retry_instruction":"Provide the missing field."}'
            )
        }
    )

    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "Return all required fields"},
        result={"answer": "partial"},
        trace=[{"tool": "example"}],
    )

    assert decision.status is CheckerDecisionEnum.RETRY
    assert len(decision.issues) == 1
    assert decision.issues[0].code == "MISSING_INFO"
    assert decision.issues[0].severity == "HIGH"
    assert decision.retry_instruction == "Provide the missing field."


@pytest.mark.asyncio
async def test_checker_fails_closed_on_provider_error():
    """
    Provider exceptions must never become ACCEPT.
    """
    provider = StubModelProvider(error=RuntimeError("provider unavailable"))
    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "test"},
        result="result",
    )

    assert decision.status is CheckerDecisionEnum.FAIL
    assert decision.issues[0].code == "CHECKER_PROVIDER_ERROR"
    assert decision.issues[0].severity == "HIGH"


@pytest.mark.asyncio
async def test_checker_fails_closed_on_invalid_json():
    """
    Malformed model output must result in FAIL.
    """
    provider = StubModelProvider(
        response={"output": "this is not valid checker json"}
    )
    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "test"},
        result="result",
    )

    assert decision.status is CheckerDecisionEnum.FAIL
    assert decision.issues[0].code == "CHECKER_INVALID_JSON"


@pytest.mark.asyncio
async def test_checker_fails_closed_on_unknown_decision():
    """
    Unsupported decision values must not be interpreted as ACCEPT.
    """
    provider = StubModelProvider(
        response={
            "output": '{"decision":"MAYBE","issues":[]}'
        }
    )
    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "test"},
        result="result",
    )

    assert decision.status is CheckerDecisionEnum.FAIL
    assert decision.issues[0].code == "CHECKER_UNKNOWN_DECISION"


@pytest.mark.asyncio
async def test_checker_parses_fenced_json():
    """
    JSON embedded inside a fenced response must still be parsed safely.
    """
    provider = StubModelProvider(
        response={
            "output": (
                "```json\n"
                '{"decision":"FAIL",'
                '"issues":[{"code":"POLICY_VIOLATION","severity":"HIGH"}]}'
                "\n```"
            )
        }
    )

    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "test"},
        result="unsafe result",
    )

    assert decision.status is CheckerDecisionEnum.FAIL
    assert decision.issues[0].code == "POLICY_VIOLATION"


@pytest.mark.asyncio
async def test_checker_rejects_invalid_issue_shape():
    """
    Malformed issue entries must fail closed instead of being silently ignored.
    """
    provider = StubModelProvider(
        response={
            "output": (
                '{"decision":"ACCEPT",'
                '"issues":"not-a-list"}'
            )
        }
    )

    checker = AgentChecker(provider)

    decision = await checker.evaluate(
        task={"description": "test"},
        result="result",
    )

    assert decision.status is CheckerDecisionEnum.FAIL
    assert decision.issues[0].code == "CHECKER_INVALID_ISSUES"