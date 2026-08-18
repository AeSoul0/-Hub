"""
@file evals/run_evals.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import asyncio
import sys
import os

# Ensure backend module is resolvable
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from harness import AgentEvaluationHarness

async def run_benchmark():
    print("=======================================")
    print(" A.U.R.O.R.A. 100/100 Benchmark Matrix ")
    print("=======================================")
    
    harness = AgentEvaluationHarness(agent_version="v1.0.0-M9")
    
    tasks = [
        {
            "input": "Calculate 25 * 4 and tell me the result.",
            "expected": "100",
            "tools": ["python_repl"]
        },
        {
            "input": "Search the web for the capital of France.",
            "expected": "paris",
            "tools": ["perform_web_search"]
        }
    ]
    
    print(f"Running {len(tasks)} benchmark tasks...")
    
    for i, t in enumerate(tasks):
        print(f"-> Task {i+1}: {t['input']}")
        res = await harness.evaluate_task(
            task_input=t["input"], 
            expected_outcome=t["expected"],
            expected_tools=t.get("tools")
        )
        status = "PASS" if res["success"] else "FAIL"
        print(f"   Status: {status} (Latency: {res['latency']:.2f}s, Tools: {res['tool_calls']})")
        
    result = harness.aggregate_metrics()
    
    print("\n--- FINAL BENCHMARK RESULTS ---")
    print(f"Version:            {result.version}")
    print(f"Success Rate:       {result.metrics.success_rate * 100:.2f}%")
    print(f"Avg Latency (p50):  {result.metrics.latency_p50:.2f}s")
    print(f"Avg Tool Calls:     {result.metrics.avg_tool_calls_per_task:.2f}")
    print(f"Policy Violations:  {result.metrics.policy_violations}")
    print("=======================================")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
