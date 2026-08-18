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
    
    def evaluate_task(self, task_input: str, expected_outcome: Any) -> Dict[str, Any]:
        """
        Executes a single evaluation task and records the outcome.
        """
        start_time = time.time()
        
        # In a real scenario, this invokes the agent via its API or internal entrypoint
        # For now, it's a stub that simulates execution and metrics gathering
        
        end_time = time.time()
        latency = end_time - start_time
        
        result = {
            "task_id": str(uuid.uuid4()),
            "task_input": task_input,
            "success": True,
            "tool_calls": 2,
            "tokens": 1500,
            "latency": latency,
            "cost": 0.0015,
            "policy_violation": False,
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
