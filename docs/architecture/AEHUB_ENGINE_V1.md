# ÆHub Agent Engine v1

## 1. Overview
The agent engine of ÆHub is A.U.R.O.R.A.'s own execution loop: an explicit
loop written in the project, with no agent framework as the authority. The
language model only proposes text and tool calls; the engine decides what
runs, records every step and can stop, pause and resume a run.

The engine runs inside the backend process (`backend/app/agent_engine/`).
`AgentEngine` (`application.py`) is the entry point; `runtime/aurora.py` is a
thin compatibility facade over it.

`AgentRuntime` (`runtime.py`) holds the loop. `_execute_task` is its
outline, and each step is a method over one `_RunLoop` state:
- `_start_run` or `_resume_run`;
- per attempt, `_run_attempt`, which covers the worker's turns, with
  `_run_proposals` for the tool calls of a turn;
- `_end_incomplete_attempt`;
- `_critic_verdict`.

Since Q1 the other parts of the runtime are mixins in their own modules:

| Module | What it does |
| --- | --- |
| `runtime_tools.py` | the tools a run sees, and each proposal through the Tool Gateway |
| `runtime_limits.py` | capabilities, run limits, spend, the stop of a run, live usage |
| `runtime_resume.py` | parking a run on an approval and resuming it |
| `runtime_state.py` | live state events, long-term memory, saving the run |
| `runtime_subagents.py` | starting a subagent (`spawn_agent`) |

## 2. Core tenets
- **The model is untrusted**: it suggests; the Tool Gateway authorizes.
- **The engine is the authority** over the loop, persistence and state.
- **Roles are separate**: the worker (Architect, Research, Fast Worker) does
  the task, an independent **Critic** on a different model checks it, the
  triage picks the role (ADR-029).
- **One door for side effects**: every tool call goes through the Tool
  Gateway, including the ones the Control Plane sends (home, skills).

## 3. The loop
1. The triage picks the role, unless the user chose one or
   `AEHUB_FORCE_ROLE` is set.
2. The worker's model gets the input rebuilt from the durable context
   (`model_input.build_input`, ADR-032) and answers with text and tool
   proposals.
3. Each proposal goes through the Tool Gateway; its observation is stored
   with the run before the next turn.
4. When the worker gives a final answer, the Critic checks it. A rejection
   sends targeted feedback back to the worker, up to the run's attempts.
5. Limits stop the run: cost (per run and monthly), active time, failed tool
   calls, subagents and modified files (`control.RunLimits`), and the stop
   buttons of the Nucleo and of the Runs page.

## 4. Subsystems

### Tool Gateway
`backend/app/runtime/tool_gateway.py`. Before anything runs:
identity → policy (tools disabled in the Control Plane included) → guardrail
(arguments, SSRF, paths) → schema → idempotency → budget → approval → audit
(fail-closed) → executor → post-guardrail (secret redaction) → audit.
The audit is a hash chain in PostgreSQL (`runtime/audit_chain.py`), shown on
the SICUREZZA page.

### Durable runs and approvals
`AgentStateManager` (`agent_engine/state/manager.py`) keeps every run in
PostgreSQL, bound to its principal, session and workspace. A HIGH-risk call
pauses the run (`WAITING_APPROVAL`); after the decision it resumes with the
same `run_id`, and a tool already executed is not executed again
(`state/idempotency.py`). An approval left undecided is denied after
`AEHUB_APPROVAL_TTL_SECONDS`.

### Subagents
The `delegate_task` tool (ADR-029) starts a subagent with at most the
parent's tools, permissions and remaining budget. It cannot delegate again,
starts tainted when the parent read untrusted content, and its cost counts
toward the parent.

### Context Manager and memory
`context.py` builds each request inside one token budget
(`AEHUB_CONTEXT_BUDGET`), in levels L0–L5: system and tools, task and Critic
feedback, trusted preferences and rules, the State Snapshot of older calls,
the recent calls, and memories from earlier sessions.
Long-term memory (`memory/store.py`, ADR-027) is scoped to workspace and
user. Retrieval fuses PostgreSQL full-text search and pgvector similarity
with Reciprocal Rank Fusion. Anything written while untrusted content is in
the run is stored as untrusted and recalled only inside a fence.

### Guardrails
1. **InputGuardrail**: refuses prompt-injection patterns in user text.
2. **ToolGuardrail**: checks arguments before a call and truncates huge
   outputs after it.
3. **OutputGuardrail**: removes secrets from what the user sees.

Untrusted tool output (web, files, MCP, imported skills) reaches the model
inside an `<untrusted_tool_output>` fence; after it, every HIGH-risk action
needs an approval.

### The app itself
On every turn the worker gets, after its fixed contract, a short context
about the app (`core/interface.app_context`, ADR-034): what ÆHub is, its
pages, the interface language, the language of the chosen voice and whether
the notice about the two is on. The `interface` skill lets Aurora change the
interface language and that notice (`set_interface_language`,
`set_voice_language_warning`): low risk, saved and audited like a change
from Settings, and every open page switches at once.

### MCP servers
`skills/mcp_bridge.py` (ADR-033) lists the tools of the allowed MCP servers
(Streamable HTTP; https, or http only to this computer) as
`mcp_<server>_<tool>` in the `mcp` skill. Each one is HIGH risk and asks for
approval on every call until the owner lowers it (`AEHUB_MCP_TOOL_RISK`); its
output is always untrusted. Each call opens its own connection, with the
host's token from the keyring when there is one.

### Models, routing and circuit breakers
Every model call goes through one `ModelProvider`, `PydanticAIAdapter`
(ADR-032): Pydantic AI makes exactly one request per turn and returns the
proposed tool calls, which run only through the Tool Gateway. Providers:
OpenAI (Responses API), OpenRouter, a local OpenAI-compatible server, Groq,
Anthropic and Google Gemini.
Each role runs on its own chain of `provider:model` (`routing.py`), and the
Critic never shares a model with a worker. If a provider fails (for example
HTTP 503), a per-target **circuit breaker** moves the call to the next model
of the chain (`FailoverProvider`); the input is rebuilt from the run's
durable observations, so no tool runs twice.

### Resources
`resources.py` guesses from its text what a task needs (light, standard,
browser, audio, vision, heavy) and gives it the RAM, run time and
parallelism of that class.

### Observability and evaluation
- **Live events**: each step is published on the event bus (Redis, or in
  process in the desktop app) and streamed to the Nucleo and the Control
  Plane over SSE.
- **Flight recorder**: every event is written to a JSONL file
  (`AEHUB_FLIGHT_RECORDER_PATH`), searchable and exportable from the SISTEMA
  page.
- **Logs and metrics**: JSON logs, OpenTelemetry traces and the Prometheus
  `/metrics` endpoint.
- **Evaluation** (`backend/app/evaluation/`, `evals/run_evals.py`): 44 cases
  run through the real engine with a scripted model and deterministic tools,
  offline and free. The release gate fails when a security case fails or a
  metric is worse than `evals/baseline.json`. `--live` uses the configured
  models instead.
