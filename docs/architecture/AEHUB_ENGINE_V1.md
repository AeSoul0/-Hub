# ÆHub Agent Engine v1 (Final Architecture)

## 1. Overview
The **ÆHub Agent Engine v1** represents a complete departure from prototype frameworks (like LangGraph) towards a highly deterministic, enterprise-grade Agent Execution Kernel. It strictly decouples the LLM from system authority.

## 2. Core Tenets
- **LLM is Untrusted**: The language model only suggests actions.
- **Kernel is Authority**: The AgentRuntime dictates execution loops, persistence, and state.
- **Strict Role Separation**: Orchestrator (Plans), Subagent (Executes), Checker (Verifies).
- **Centralized Side-Effects**: ALL execution occurs solely through the ToolGateway v2.

## 3. The Orchestration Loop
The heart of the Engine operates on a native Worker -> Checker -> Retry loop:
1. Worker (Adapter) generates a response and proposes tools.
2. ToolGateway executes tools and returns observations.
3. Checker (Independent Adapter) verifies the final output.
4. If rejected, the Worker receives targeted feedback for a retry loop up to a strict max_attempts budget.

## 4. Subsystem Capabilities
### Tool Gateway v2
Before execution, every request passes through:
Validation -> Identity -> Permission -> Risk -> Budget -> Approval -> Idempotency -> Sandbox -> Audit

### Durable Runs & Approvals
The AgentStateManager persists the AgentRun model to disk (durable_runs.json). 
Tasks requiring human approval are paused (WAITING_APPROVAL) and safely recovered without context loss. If a process crashes during a retry loop, it restarts exactly where it died.

### Multi-Agent Orchestration
spawn_agent dynamically spins up specialized workers governed by a restrictive SubagentCapabilitySet. This guarantees child agents do not inherit admin privileges from the parent orchestrator.

### Memory Engine v1
Implements Semantic, Episodic, and Execution memory tracking.
Retrieval relies on: Relevance * Importance * Confidence * Recency Decay.
Strictly isolated by workspace_id.

### Guardrails Layer
1. **InputGuardrail**: Blocks prompt injection strings before they hit the LLM.
2. **ToolGuardrail**: Pre-execution parameter blocking and Post-execution massive output truncation.
3. **OutputGuardrail**: Strips sensitive system variables from user-facing responses.

### Model Adapters & Circuit Breaking
LangGraph was removed in favor of the unified ModelProvider layer (e.g., OpenAIAdapter, GroqAdapter).
The Orchestrator, Worker, and Checker can each operate on different providers.
If the primary provider crashes (e.g., HTTP 503), the Kernel's native **Circuit Breaker** automatically reroutes the prompt to a fallback adapter.

### Observability & Evaluation
The EventDispatcher creates deterministic Flight Recorder logs (JSONL). The Phase 10 EvaluationEngine leverages an LLM-as-a-Judge to parse these traces against a 140+ test case dataset to certify the Engine's Definition of Done.
