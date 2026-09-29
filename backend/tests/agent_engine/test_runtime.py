"""
@file backend\tests\agent_engine\test_runtime.py
@description Core implementation of test_runtime.py.

Implements core logic and architectural definitions.
"""

import pytest
import asyncio
from datetime import datetime
from app.agent_engine.runtime import AgentRuntime, ToolGateway
from app.agent_engine.models import CheckerDecision, CheckerDecisionEnum, ToolProposal, ToolResult
from app.agent_engine.errors import MaxTurnsReachedError, TaskTimeoutError

class CancellationToken:
    def __init__(self):
        self.is_cancelled = False
    def cancel(self):
        self.is_cancelled = True

class MockOrchestrator:
    run_id = "orch_1"

class MockWorker:
    run_id = "worker_1"
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def generate(self, context):
        if self.call_count >= len(self.responses):
            raise Exception("No more mocked responses")
        resp = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

class MockChecker:
    run_id = "checker_1"
    def __init__(self, decisions):
        self.decisions = decisions
        self.call_count = 0

    async def evaluate(self, task, result):
        if self.call_count >= len(self.decisions):
            raise Exception("No more mocked decisions")
        dec = self.decisions[self.call_count]
        self.call_count += 1
        if isinstance(dec, Exception):
            raise dec
        return dec

class MockToolGateway(ToolGateway):
    def __init__(self, tools_dict):
        self.tools = tools_dict

    async def execute(self, proposal: ToolProposal):
        if proposal.tool_name not in self.tools:
            raise Exception(f"Tool {proposal.tool_name} not found")
        return self.tools[proposal.tool_name](proposal.arguments)

def test_task_without_tool():
    runtime = AgentRuntime()
    worker = MockWorker([{"output": "success"}])
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert result == "success"

def test_task_with_1_tool():
    def mock_tool(args):
        return ToolResult(tool_call_id="1", result="tool_success")
    gateway = MockToolGateway({"my_tool": mock_tool})
    runtime = AgentRuntime(tool_gateway=gateway)
    
    worker = MockWorker([
        {"tool_proposals": [ToolProposal(tool_call_id="1", tool_name="my_tool", arguments={}, run_id="r")]},
        {"output": "final result after tool"}
    ])
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert result == "final result after tool"

def test_task_with_5_consecutive_tools():
    def mock_tool(args):
        return ToolResult(tool_call_id="1", result="tool_success")
    gateway = MockToolGateway({"my_tool": mock_tool})
    runtime = AgentRuntime(tool_gateway=gateway)
    
    responses = [{"tool_proposals": [ToolProposal(tool_call_id=str(i), tool_name="my_tool", arguments={}, run_id="r")]} for i in range(5)]
    responses.append({"output": "success after 5 tools"})
    
    worker = MockWorker(responses)
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert result == "success after 5 tools"

def test_inexistent_tool():
    gateway = MockToolGateway({})
    runtime = AgentRuntime(tool_gateway=gateway)
    
    worker = MockWorker([
        {"tool_proposals": [ToolProposal(tool_call_id="1", tool_name="fake_tool", arguments={}, run_id="r")]},
        {"output": "handled error"}
    ])
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert result == "handled error"

def test_timeout():
    runtime = AgentRuntime()
    class SlowWorker:
        async def generate(self, context):
            await asyncio.sleep(0.5)
            return {"output": "slow"}
    worker = SlowWorker()
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    with pytest.raises(TaskTimeoutError):
        asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker, timeout=0.1))

def test_cancellation():
    runtime = AgentRuntime()
    worker = MockWorker([{"output": "success"}])
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    token = CancellationToken()
    token.cancel()
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker, cancellation_token=token))
    assert result is None

def test_max_turns():
    runtime = AgentRuntime()
    worker = MockWorker([{"tool_proposals": [ToolProposal(tool_call_id="1", tool_name="tool", arguments={}, run_id="r")]}] * 4)
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    with pytest.raises(MaxTurnsReachedError):
        asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker, max_turns=3))

def test_model_failure():
    runtime = AgentRuntime()
    worker = MockWorker([Exception("LLM crashed")])
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.ACCEPT)])
    with pytest.raises(MaxTurnsReachedError) as exc_info:
        asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert "Worker failed: LLM crashed" in str(exc_info.value)

def test_checker_reject_and_retry():
    runtime = AgentRuntime()
    worker = MockWorker([
        {"output": "bad result"},
        {"output": "good result"}
    ])
    checker = MockChecker([
        CheckerDecision(status=CheckerDecisionEnum.REJECT, retry_instruction="fix it"),
        CheckerDecision(status=CheckerDecisionEnum.ACCEPT)
    ])
    result = asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert result == "good result"

def test_max_attempts():
    runtime = AgentRuntime()
    worker = MockWorker([{"output": "bad result"}] * 3)
    checker = MockChecker([CheckerDecision(status=CheckerDecisionEnum.REJECT, retry_instruction="fix it")] * 3)
    with pytest.raises(MaxTurnsReachedError):
        asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker, max_attempts=2))

def test_checker_failure():
    runtime = AgentRuntime()
    worker = MockWorker([{"output": "success"}])
    checker = MockChecker([Exception("Checker crashed")])
    with pytest.raises(MaxTurnsReachedError) as exc_info:
        asyncio.run(runtime.execute_task({"goal": "test"}, MockOrchestrator(), worker, checker))
    assert "Checker failed: Checker crashed" in str(exc_info.value)
