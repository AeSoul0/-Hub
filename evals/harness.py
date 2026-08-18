"""
@file evals/harness.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import time
import uuid
from typing import Any, Dict, List
from pydantic import BaseModel

class EvalMetric(BaseModel):
    success_rate: float
    avg_tool_calls_per_task: float
    avg_tokens_per_task: float
    latency_p50: float
    latency_p95: float
    cost_per_task: float
    policy_violations: int
    recovery_rate: float

class EvaluationResult(BaseModel):
    version: str
    metrics: EvalMetric
    tasks_evaluated: int
    raw_results: List[Dict[str, Any]]

class AgentEvaluationHarness:
    def __init__(self, agent_version: str):
        self.agent_version = agent_version
        self.results = []
    
    async def evaluate_task(self, task_input: str, expected_outcome: str, expected_tools: List[str] = None) -> Dict[str, Any]:
        """
        Executes a single evaluation task and records the outcome.
        """
        from app.runtime.aurora import run_aurora_agent
        from app.core.security import Principal, RoleEnum
        
        start_time = time.time()
        
        # We use a synthetic principal for evals
        principal = Principal(id="eval_user", role=RoleEnum.ADMIN, workspace_id="default")
        session_id = f"eval-{uuid.uuid4()}"
        
        try:
            final_state = await run_aurora_agent(session_id, task_input, principal)
            messages = final_state.get("messages", [])
            output = messages[-1].content if messages else ""
            
            # Count tool calls
            tool_calls = 0
            called_tools = []
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_calls += len(msg.tool_calls)
                    called_tools.extend([tc["name"] for tc in msg.tool_calls])
                    
            # Basic assertion logic: Check if expected outcome keywords are in output
            success = expected_outcome.lower() in output.lower()
            
            # Check if expected tools were used
            if expected_tools:
                success = success and all(t in called_tools for t in expected_tools)
                
            error = False
            
        except Exception as e:
            success = False
            error = True
            output = str(e)
            tool_calls = 0
            
        end_time = time.time()
        latency = end_time - start_time
        
        result = {
            "task_id": session_id,
            "task_input": task_input,
            "success": success,
            "tool_calls": tool_calls,
            "tokens": 0, # Could be injected from LangSmith if connected
            "latency": latency,
            "cost": 0.0,
            "policy_violation": error,
            "recovered": False
        }
        self.results.append(result)
        return result
        
    def aggregate_metrics(self) -> EvaluationResult:
        if not self.results:
            return None
            
        successes = sum(1 for r in self.results if r["success"])
        tool_calls = sum(r["tool_calls"] for r in self.results)
        tokens = sum(r["tokens"] for r in self.results)
        costs = sum(r["cost"] for r in self.results)
        violations = sum(1 for r in self.results if r["policy_violation"])
        recoveries = sum(1 for r in self.results if r["recovered"])
        
        latencies = sorted(r["latency"] for r in self.results)
        p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
        
        n = len(self.results)
        metric = EvalMetric(
            success_rate=successes / n,
            avg_tool_calls_per_task=tool_calls / n,
            avg_tokens_per_task=tokens / n,
            latency_p50=p50,
            latency_p95=p95,
            cost_per_task=costs / n,
            policy_violations=violations,
            recovery_rate=recoveries / successes if successes else 0.0
        )
        
        return EvaluationResult(
            version=self.agent_version,
            metrics=metric,
            tasks_evaluated=n,
            raw_results=self.results
        )

    @staticmethod
    def compare_versions(baseline: EvaluationResult, candidate: EvaluationResult) -> Dict[str, float]:
        """
        Compares Agent version N with Agent version N-1.
        Returns the delta for each key metric.
        """
        return {
            "success_rate_delta": candidate.metrics.success_rate - baseline.metrics.success_rate,
            "latency_p50_delta": candidate.metrics.latency_p50 - baseline.metrics.latency_p50,
            "cost_delta": candidate.metrics.cost_per_task - baseline.metrics.cost_per_task
        }
