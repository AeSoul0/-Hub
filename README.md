# ÆHub — AeSoul Digital Hub

> A full-stack AI orchestration platform for building, running, and extending tool-using agents with persistent memory, web search, sandboxed execution, and multi-agent delegation.

[![GitHub](https://img.shields.io/badge/GitHub-AeSoul0%2F--Hub-181717?logo=github)](https://github.com/AeSoul0/-Hub)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=next.js)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://www.docker.com/)

## Overview
## Architecture: ÆHub Agent Engine v1

The system has been completely rebuilt into a deterministic, enterprise-grade Agent Execution Kernel, replacing legacy black-box frameworks (e.g., LangGraph) with explicit control loops:

1. **Agent Kernel**: Operates on a native Orchestration Loop (Worker -> Checker -> Retry), entirely isolating the planner from the executor and the verifier.
2. **Tool Gateway v2**: Centralizes all side-effects. Before any tool runs, it passes through strict Validation -> Identity -> Permission -> Risk -> Budget -> Approval -> Idempotency -> Sandbox -> Audit layers.
3. **Policy Engine**: Decouples formal authorization from the LLM, ensuring that subagents only operate within strictly delegated SubagentCapabilitySet bounds.
4. **Durable Checkpointing**: The AgentStateManager dumps all states to disk, allowing paused executions (Human-in-the-Loop) and instantaneous recovery from fatal process crashes midway through a task.
5. **Guardrails**: A 3-layer architecture (InputGuardrail -> ToolGuardrail -> OutputGuardrail) defends against prompt injection, blocks catastrophic parameters (e.g., 
m -rf), and prevents secret exfiltration.
6. **Memory Engine v1**: Manages partitioned Episodic, Semantic, and Execution memory via pgvector, retrieved dynamically using a hybrid scoring algorithm (Relevance * Importance * Confidence * Recency Decay).
7. **Resource Management**: The Phase 13 ResourceManager classifies tasks (Light, Heavy, Vision, etc.) and dynamically budgets RAM, concurrency, and timeouts prior to execution.
8. **Model Adapters & Circuit Breakers**: Completely abstracts LLMs into the ModelProvider interface. Orchestrator, Worker, and Checker can run on completely different providers. If an API fails (e.g., OpenAI 503), the Engine's native **Circuit Breaker** automatically reroutes the task to a fallback provider (e.g., Groq) without dropping the state.


ÆHub is a full-stack platform for experimenting with and operating **AI agents** that can reason over a task, invoke tools, maintain session context, delegate work to specialized subagents, and interact with external services.

The project combines a **Next.js frontend** with a **FastAPI backend** and an advanced proprietary agent runtime (**ÆHub Agent Engine v1**) featuring dynamic resource management, explicit orchestration, strict security gateways, and unified multi-provider adapters (OpenAI, Groq, Anthropic, etc.).

Rather than treating an LLM as a simple text-generation endpoint, ÆHub models the LLM as a decision-making component inside a broader runtime:

```text
User
  ↓
API / Realtime Interface
  ↓
A.U.R.O.R.A. Agent Runtime
  ↓
Reasoning + Tool Selection
  ↓
Tools / Skills / Subagents
  ↓
Observations + Memory
  ↓
Next Agent Step
  ↓
Final Response
```

### What problem does it solve?

Traditional LLM integrations usually stop at:

```text
Prompt → LLM → Text
```

That model becomes limiting when an application needs to:

* execute real operations;
* search external information;
* retain persistent user context;
* delegate complex tasks;
* run controlled code;
* expose capabilities through reusable tools;
* stream runtime events;
* enforce security boundaries around agent actions.

ÆHub addresses those requirements by providing an extensible agent architecture in which **skills, tools, memory, workflows, workers, and subagents are separate components**.

### Current use cases

The current codebase supports or provides foundations for:

* conversational AI orchestration;
* web research;
* persistent semantic and procedural memory;
* task and event memory;
* controlled Python and shell execution;
* specialized research subagents;
* supervisor-style delegation;
* real-time event streaming;
* scheduled/proactive workloads;
* voice input and output;
* browser and automation-oriented workflows;
* MCP integration as an extensibility layer.

---

# Key Features

| Capability                 | Status | Description                                                                                                   |
| -------------------------- | ------ | ------------------------------------------------------------------------------------------------------------- |
| Autonomous task execution  | ✅      | LangGraph-based agent loop capable of iterative tool execution                                                |
| Tool / function calling    | ✅      | LangChain tools are dynamically bound to the LLM                                                              |
| Planning and reasoning     | ✅      | Agent decisions emerge from the LangGraph execution cycle                                                     |
| Short-term memory          | ✅      | LangGraph message state                                                                                       |
| Persistent memory          | ✅      | PostgreSQL-backed semantic, episodic, and procedural memory (with pgvector embedding)                         |
| RAG                        | ✅      | Hybrid search (full text + pgvector) over memory and the documents of the working folder, with cited sources |
| Multi-agent collaboration  | ✅      | Supervisor skill delegates tasks dynamically using deterministic role-based Llama models                      |
| Human-in-the-loop          | 🟡     | Risk metadata and approval flags exist; full approval workflow is not yet enforced end-to-end                 |
| Monitoring / observability | ✅      | JSON Semantic Logging, OpenTelemetry tracing, and Prometheus `/metrics` exporter implemented                  |
| Extensibility              | ✅      | Skill registry, dynamic discovery, MCP bridge, tool metadata, and modular runtime                             |
| Security / Identity        | ✅      | RBAC Policy Engine, strict Docker Sandboxing (cpus, pids-limit, read-only), and Tool Gateway                  |
| Durable execution          | ✅      | Run state, approvals and idempotency in PostgreSQL; Redis is the event bus (no worker queue, see ADR-019)     |

---

# Architecture

ÆHub follows a decoupled client-server architecture with an agent runtime embedded in the backend.

```mermaid
flowchart TD
    User[User / Browser]
    Frontend[Next.js Frontend]
    API[FastAPI API]
    Agent[A.U.R.O.R.A. Agent]
    Graph[LangGraph Runtime]
    LLM[Groq LLM<br/>Llama 3 70B]
    Registry[Skill Registry]
    Tools[Tools / Skills]
    Memory[Aurora Memory Manager]
    Checkpoint[(PostgreSQL Checkpoints)]
    DB[(PostgreSQL)]
    Redis[(Redis)]
    Search[Web Search]
    Sandbox[Sandbox Execution]
    Subagents[Specialized Subagents]
    Events[EventBus / SSE]
    External[External Services]

    User --> Frontend
    Frontend --> API
    API --> Agent
    Agent --> Graph
    Graph --> LLM
    LLM -->|tool calls| Registry
    Registry --> Tools

    Tools --> Search
    Tools --> Sandbox
    Tools --> Subagents
    Tools --> External

    Agent --> Memory
    Memory --> DB
    Graph --> Checkpoint

    API --> Events
    Events --> Frontend

    API --> Redis
    Agent --> Redis
```

## Core components

### Frontend

The frontend is a **Next.js application** using React, TypeScript and Tailwind CSS. Fonts are bundled from npm, so it loads nothing from third parties.

- **The Nucleo** (`/`, ADR-022) is the home:
  - a dotted sphere in the centre reacts to what the engine does: model calls, tool calls, subagents as small moons, approvals in amber, the microphone, the spoken reply;
  - the conversation sits on the left and the engine's live events on the right; both panes grow from their top edge and can be hidden;
  - pending approvals are decided there;
  - the **RUN** tab of the right pane follows each run of the session (ADR-023): cost, active time, failed tool calls and written files against the per-run limits, live, with a stop button and the run's timeline; **FERMA TUTTO** in the top bar stops every run (a second click confirms) and **RIPRENDI** lifts the stop.
- **The Control Plane** (`/control-plane`) has runs, approvals, memory, documents, tools, skills, security, voice, settings and setup, all in the Nucleo's style; the history of the runs filters by text, status, period and subagents.
- **Settings** (ADR-025) choose the LLM of each role (Architect, Research, Critic, Fast Worker, Triage) with its fallbacks, suggesting each provider's models (OpenRouter with prices), and refuse a Critic that shares a model with another role. They also hold keys, default models, the local server, prices, budget and limits, the approval window, the circuit breaker and the context budget, all applied without a restart.
- **Tools and skills** (ADR-026):
  - **STRUMENTI** lists every skill and tool with its risk, approval, network and file access, and whether it returns untrusted content. It switches tools off: a disabled tool is never shown to the agent and is refused if proposed. The page also sets the skill index and the allowed MCP servers, and shows the tools' folders, the API host names and the sandbox.
  - **SKILL** imports skills in the open `SKILL.md` format (Claude Code, Codex, OpenClaw) from an https link (a GitHub page is turned into its raw file) or a file. Only the text is imported, and the skill starts off. The page shows the whole text and flags patterns to check before it can be turned on: download-and-run commands, encoded blobs, instruction overrides, secrets, bundled files and links. The agent reads an enabled skill through the `use_skill` tool as untrusted content, so after reading it every high-risk action waits for an approval.
  - **SICUREZZA** shows the audit hash chain, the log (Control Plane changes included) filtered by decision and tool, and which entries returned untrusted content.
  - **The run view** also lists the tools the skill index picked for the run.
- **Memory and documents** (ADR-027):
  - **MEMORIA** turns long-term memory on or off and sets the similarity threshold, the embedder and its model. After an embedder change it recomputes the old vectors.
  - On the same page you add facts, preferences and rules, search with the engine's hybrid retrieval, and filter by kind and trust. A memory can be edited in place, forgotten, or vouched for ("Mi fido", audited) when it was written from untrusted content. All untrusted memories can be forgotten at once.
  - **DOCUMENTI** shows the working folder and its index. It syncs, uploads a file into the folder, sets the size limit and searches the index.
  - **Citations** `[doc: file#lines]` in answers (Nucleo and run view) open the cited passage.
- **How much of the backend the interface controls** is tracked in `docs/frontend-coverage.md`; `v1.0.0` waits for 100%.

The look is a deep-blue space theme with squircle corners. The visual reference is `docs/design/hud-prototype.html`.

The frontend development server is configured to run on port `2003`.

### FastAPI backend

The backend exposes the application's HTTP and WebSocket interfaces.

`backend/main.py` is responsible for application initialization, router registration, authentication middleware, CORS configuration, event streaming, voice processing, and runtime startup.

The API includes:

* REST endpoints;
* WebSocket communication;
* Server-Sent Events;
* agent orchestration endpoints;
* voice processing.

### A.U.R.O.R.A. runtime

A.U.R.O.R.A. is the project's main agent runtime:

**Autonomous Uplink & Real-time Operations Robotic Assistant**

The runtime is implemented with **LangGraph** and maintains an explicit state containing messages, session information, and current intent.

The graph follows a loop similar to:

```text
Agent
  ↓
LLM Decision
  ↓
Tool Call?
 ┌───────────────┐
 │ Yes           │ No
 ↓               ↓
Tool Execution   END
 ↓
Observation
 ↓
Agent
```

### LLM

The current runtime uses **Groq's `llama3-70b-8192`** through `langchain-groq`.

The LLM is responsible for:

* interpreting user intent;
* generating responses;
* deciding when to invoke tools;
* producing tool arguments;
* synthesizing tool observations into the next action or final response.

### Skill Registry

Skills are modular capabilities dynamically loaded from `app.skills`.

The registry:

1. discovers skill modules;
2. loads modules exposing `get_skill()`;
3. registers tools;
4. aggregates tool definitions;
5. aggregates system-prompt extensions;
6. exposes the resulting capability set to the agent.

This allows new capabilities to be added without modifying the central agent graph.

### Memory

The memory layer currently provides:

* working memory through LangGraph state;
* conversational persistence through PostgreSQL checkpoints;
* semantic memory;
* episodic memory;
* procedural memory;
* document search over the working folder (see [Asking about your documents](#asking-about-your-documents)).

### PostgreSQL

PostgreSQL is used for durable state and agent persistence, including LangGraph checkpoints and structured memory records.

### Redis

Redis is provisioned by Docker Compose as a cache/event-oriented infrastructure component.

### External services

Depending on enabled skills and features, ÆHub can interact with:

* Groq;
* DuckDuckGo search;
* external MCP services;
* browser automation services;
* other application-specific integrations.

---

# How It Works

A typical agent execution follows this sequence.

### 1. Input

The user sends a natural-language request through the API or frontend.

Example:

```text
Find the latest information about a technology and summarize the important changes.
```

### 2. Security validation

Incoming text is processed by the prompt-injection filter before being forwarded to the main agent runtime.

Known suspicious patterns are rejected.

### 3. Session resolution

The request is associated with a `session_id`.

This allows memory and checkpoints to remain isolated between sessions.

### 4. Context retrieval

The agent runtime retrieves relevant persistent memory:

* known user facts;
* procedural preferences;
* previous conversational state.

### 5. Reasoning

The LLM receives:

* system instructions;
* persistent memory context;
* active skill instructions;
* current user messages.

It determines whether the task can be answered directly or requires a tool.

### 6. Tool selection

If a tool is required, LangGraph routes the execution to a `ToolNode`.

Examples include:

* web search;
* memory operations;
* Python execution;
* shell execution;
* supervisor delegation.

### 7. Tool execution

The selected tool executes outside the LLM.

The result becomes an observation available to the next agent step.

### 8. Next action

The LLM evaluates the observation and decides whether to:

* execute another tool;
* delegate additional work;
* continue reasoning;
* produce the final answer.

### 9. Persistence

Conversation and memory data can be persisted using PostgreSQL.

### 10. Final response

The final agent response is returned through the API and can also be converted to speech.

---

# Project Structure

The repository is organized as a frontend/backend monorepo.

```text
-Hub/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── orchestrator.py
│   │   │   └── subagents/
│   │   │       └── base.py
│   │   │
│   │   ├── api/
│   │   │   ├── approvals.py
│   │   │   ├── auth.py
│   │   │   ├── memory.py
│   │   │   ├── realtime.py
│   │   │   └── runs.py
│   │   │
│   │   ├── core/
│   │   │   ├── db.py
│   │   │   ├── event_bus.py
│   │   │   └── security.py
│   │   │
│   │   ├── memory/
│   │   │   └── manager.py
│   │   │
│   │   ├── runtime/
│   │   │   └── aurora.py
│   │   │
│   │   ├── skills/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── memory_skill.py
│   │   │   ├── web_search.py
│   │   │   ├── sandbox_skill.py
│   │   │   ├── browser_skill.py
│   │   │   └── mcp_bridge.py
│   │   │
│   │   └── workers/
│   │       └── sandbox.py
│   │
│   ├── main.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── dockerfile
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   ├── next.config.js
│   ├── tsconfig.json
│   └── dockerfile
│
├── data/
├── docker-compose.yaml
├── .gitignore
└── README.md
```

## Directory responsibilities

| Directory               | Responsibility                                                  |
| ----------------------- | --------------------------------------------------------------- |
| `backend/app/agents`    | Main orchestrator and subagent abstractions                     |
| `backend/app/api`       | FastAPI routers and external API boundaries                     |
| `backend/app/core`      | Shared infrastructure such as persistence, events, and security |
| `backend/app/memory`    | Persistent agent memory services                                |
| `backend/app/runtime`   | Tool Gateway, durable task state and audit hash chain           |
| `backend/app/skills`    | Modular agent capabilities and tools                            |
| `backend/app/workers`   | Docker sandbox for code execution                               |
| `frontend/src`          | Next.js application code                                        |
| `data`                  | Local persistence volumes used by Docker Compose                |

---

# Installation

## Prerequisites

Recommended development environment:

* Python 3.12 (the version of the backend image and of CI)
* Node.js compatible with the project's Next.js version
* npm
* Docker
* Docker Compose
* Git

An LLM provider credential is also required for the current agent runtime.

### Clone the repository

```bash
git clone https://github.com/AeSoul0/-Hub.git
cd -Hub
```

## Option A — Docker Compose

The repository includes services for:

* backend;
* frontend;
* PostgreSQL;
* Redis.

### First run (about ten minutes)

```bash
python scripts/aehub.py setup    # or: make setup
python scripts/aehub.py up       # or: make up
```

Then open http://localhost:3000/control-plane, sign in with the key printed by `python scripts/aehub.py login-key`, and follow the first-run setup: models (Worker and a different Critic), prices, budget, and a final check. Everything it sets can be changed later in **Settings** without a restart.

The launcher (`scripts/aehub.py`, Python standard library only) keeps every secret in the **OS keyring** — Windows Credential Manager, macOS Keychain or the Linux Secret Service — never in a file:

| Command | What it does |
| --- | --- |
| `setup` | Creates the database password (`.env`) and the Control Plane login key; asks for the provider keys (hidden input) and the agent's working folder; moves any key found in `backend/.env` into the keyring and removes it from the file. |
| `up` / `down` | Starts / stops the stack. `up` reads the keys from the keyring and hands them to `docker compose` through its process environment; `docker-compose.yaml` passes them to the backend container. |
| `secrets` | Which keys are set (never their values). |
| `login-key` | Prints the Control Plane login key. |

On Windows the launcher talks to Credential Manager directly. Elsewhere it needs the `keyring` package (`pip install keyring`), which it also prefers on Windows when installed; both read the same entries (service `aehub`). `start.ps1` runs `setup` on the first start and `up` afterwards.

Keys passed by the launcher win over `backend/.env`, which now holds only non-secret settings. Running `docker compose up` by hand starts the backend without keys (it exits without a login key); put them in your shell environment or use the launcher.

### One-command demo

```bash
make demo
```

`make demo` (or `python scripts/demo.py`, which needs only the Python standard library) runs the whole loop on a clean machine:

1. through the launcher, creates the database password and the login key, and asks once (without echo) for the model API key, which goes to the OS keyring;
2. starts PostgreSQL, Redis, backend and frontend with Docker Compose and waits for `/health`;
3. if the Worker and Critic models are not configured, asks for them and saves them through the Settings API; then sends a real command that needs a HIGH-risk tool (a shell command in the sandbox), so the run stops for approval;
4. waits while you approve or deny it from http://localhost:3000;
5. prints the outcome and its cost.

The backend container builds its `POSTGRES_URL` from `POSTGRES_PASSWORD` in the root `.env`, so the password lives in one place; the database is reachable only on this machine. The agent's working folder (`./workspace`, or the one chosen with `setup`, stored as `AEHUB_WORKSPACE_DIR` in `.env`) is mounted into the backend container.

The current Compose configuration maps:

```text
Frontend  → http://localhost:3000
Backend   → http://localhost:3002
PostgreSQL → localhost:5432
Redis     → localhost:6379
```

**Healthcheck**: The backend service includes a Docker `HEALTHCHECK` that probes `http://localhost:3002/health` every 30 seconds. This ensures the container is marked unhealthy if the API does not respond.

## Option B — Local backend development

Install backend dependencies:

```bash
cd backend
python -m venv .venv
```

Activate the environment.

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install packages:

```bash
pip install -r requirements.txt
```

Start the API:

```bash
uvicorn main:app --host 0.0.0.0 --port 3002
```

## Local frontend development

```bash
cd frontend
npm install
npm run dev
```

The frontend development server runs on:

```text
http://localhost:2003
```

## Option C — Desktop app (Windows)

The desktop app needs no Docker: one installer holds the engine, its own PostgreSQL with pgvector and the frontend (roadmap M14, `docs/adr/ADR-020-Runtime-desktop.md`).

- **Install:** run the `AEHub_*-setup.exe` from the GitHub Release of a version tag, or from the `aehub-windows-installer` artifact of the CI (`desktop-windows` job). It installs for the current user, without administrator rights. Without an Authenticode certificate in the CI secrets it is not code-signed, so Windows SmartScreen asks for confirmation.
- **Updates:** on start the app looks for a newer release, signed with the updater's key, and installs it only if you say yes. Releases are published by the CI when `TAURI_SIGNING_PRIVATE_KEY` is among its secrets.
- **First start:** the app creates its database in `%LOCALAPPDATA%\AEHub` and its working folder in `Documents\AEHub`, then opens the Control Plane already logged in. Add a provider key on the setup page: it goes to the Windows Credential Manager, never to a file. Then pick models, prices and budget as with Docker.
- **How it runs:** the window starts `backend/desktop.py`, which runs Postgres and the API on `127.0.0.1` on ports chosen at every start, with live events in-process instead of Redis. The window logs in with a one-time token. Closing the window stops everything.
- **Memory:** the desktop app uses the `hash` embedder, which needs no model download and has weaker recall, until the local embedder is decided (ADR-020).

Building the installer locally needs Rust, Node.js 20, Python 3.12, Visual Studio Build Tools and a PostgreSQL install with pgvector:

```bash
cd frontend && AEHUB_STATIC_EXPORT=1 npm run build && cd ..
python desktop/scripts/bundle.py --pg-root "C:/Program Files/PostgreSQL/17"
python desktop/scripts/smoke_sidecar.py
cd desktop && npm ci && npx tauri build
```

---

# Configuration

Configuration has three homes:

* **Secrets** (provider API keys, the login key) — the OS keyring, through the launcher (see *First run*). The backend reads them from its environment.
* **Settings** — model roles, prices, budget and run limits, voice, the tool settings (disabled tools, skill index, MCP servers), memory (on/off, similarity, embedder) and the document size limit. Edited in the Control Plane (**Settings**, `GET`/`PUT /api/settings`), stored in the `app_settings` table, applied from the next run without a restart. A setting never edited falls back to the environment variable of the same name, then to its default, so `backend/.env`, CI and tests keep working. Every change is validated as a whole (a Critic equal to a Worker is refused before it is saved) and recorded in the audit log as `settings.update`.
* **Infrastructure** — database, Redis, CORS, paths: environment only (`backend/.env`, root `.env` for Compose).

At startup the backend logs one line per configuration problem (`[CONFIG ERROR]`, `[CONFIG WARNING]`, …): Critic equal to a Worker, a provider without its key, models without a price, a run limit above the monthly budget, a missing working folder. The Settings page shows the same list. The API starts anyway, so the page can fix what it can; runs are refused while an error remains.

## Backend `.env` (local development)

Example for running the backend outside Docker:

```env
# PostgreSQL
POSTGRES_URL=postgresql://aehub_user:replace_password@localhost:5432/aehub_db

# Optional Redis infrastructure
REDIS_URL=redis://localhost:6379/0
```

Outside Docker, put the keys in your shell environment (for example `AEHUB_SECRET_KEY`, `OPENAI_API_KEY`) rather than in this file. Voice needs no key: it runs on this machine (see Voice).

## Frontend `.env.local`

Use the variables expected by the frontend implementation in your deployment.

A typical configuration may look like:

```env
NEXT_PUBLIC_API_URL=http://localhost:3002
```

Do not expose private backend secrets through `NEXT_PUBLIC_*` variables.

## Configuration notes

| Variable              | Purpose                                                     |
| --------------------- | ----------------------------------------------------------- |
| `AEHUB_SECRET_KEY`    | Control Plane login key (keyring; required, the API exits without it) |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | Provider keys (keyring)                   |
| `AEHUB_MQTT_PASSWORD` | Password of the home MQTT broker (keyring; optional)       |
| `ELEVENLABS_API_KEY`  | Optional cloud voice (keyring; ADR-024)                    |
| `POSTGRES_URL`        | PostgreSQL connection string used by the agent runtime      |
| `REDIS_URL`           | Redis connection information                                |
| `NEXT_PUBLIC_API_URL` | Public frontend endpoint for backend communication          |

## Agent engine settings

The model, price and limit variables below (`OPENAI_MODEL`, `AEHUB_CHECKER_MODEL`, `AEHUB_MODEL_ROLES`, `AEHUB_MODEL_PRICES`, `AEHUB_DEFAULT_MODEL_PRICE`, `AEHUB_RUN_*`, `AEHUB_MONTHLY_BUDGET`, `AEHUB_BUDGET_WARNING_RATIO`) are also editable in Settings; a value set there wins over the environment.

| Variable | Purpose | Default |
| --- | --- | --- |
| `AEHUB_MODEL_ROLES` | Models per role (spec 4.1) as JSON: `{"architect": ["openrouter:<model>", "openai:<model>"], "critic": ["local:<model>"], ...}`. Roles: `architect`, `research`, `critic`, `fast_worker`, `triage`. The first entry is the primary model, the others are fallbacks. Providers: `openai`, `openrouter`, `local`. | every role uses `OPENAI_MODEL` on `openai` |
| `AEHUB_CHECKER_MODEL` | Critic model when `AEHUB_MODEL_ROLES` does not set `critic`. The Critic must differ from every Implementer model, otherwise agent runs are refused. | none |
| `OPENROUTER_API_KEY` | Key for the `openrouter` provider | none |
| `AEHUB_LOCAL_BASE_URL` | OpenAI-compatible local server for the `local` provider (Ollama, LM Studio); also in Settings, key `AEHUB_LOCAL_API_KEY` in the keyring | `http://localhost:11434/v1` |
| `AEHUB_FORCE_ROLE` | Skip triage and run every task with this role (also in Settings) | none |
| `AEHUB_BREAKER_THRESHOLD` / `AEHUB_BREAKER_COOLDOWN_SECONDS` | Consecutive failures before a provider is skipped, and how long it stays skipped (also in Settings) | `3` / `60` |
| `AEHUB_MODEL_PRICES` | Prices as JSON, USD per 1M tokens: `{"<model>": {"input": 1.0, "output": 4.0}}`. Unpriced models use a deliberately high fallback price and are flagged as estimated. | none |
| `AEHUB_DEFAULT_MODEL_PRICE` | Fallback price `input,output` | `15,60` |
| `AEHUB_RUN_MAX_COST` / `AEHUB_MONTHLY_BUDGET` | Per-run hard stop and monthly cap, in USD (warning at `AEHUB_BUDGET_WARNING_RATIO`) | `2` / `30` (`0.8`) |
| `AEHUB_RUN_TIMEOUT_SECONDS` | Limit on a run's active execution time; waiting for an approval does not count. `0` disables it | `900` |
| `AEHUB_RUN_MAX_FAILED_TOOL_CALLS` | Failed tool calls after which a run stops (`LIMIT_EXCEEDED`), e.g. a loop on a failing tool or test. `0` disables it | `10` |
| `AEHUB_RUN_MAX_FILES_MODIFIED` | Distinct files a run may change through tools flagged `modifies_files`; a call on one more file is refused. `0` disables it | `20` |
| `AEHUB_APPROVAL_TTL_SECONDS` | An approval left undecided this long is denied (30 s – 24 h; also in Settings) | `300` |
| `AEHUB_CONTEXT_BUDGET` | Token budget of one model request, split across the Context Manager levels L0–L5 (spec 4.2; also in Settings) | `88000` |
| `AEHUB_SNAPSHOT_EVERY` | Tool calls between State Snapshots; older calls leave the recent window and are summarized (clamped to 10–20) | `15` |
| `AEHUB_MEMORY_ENABLED` | Cross-session long-term memory: recall at run start, indexing of accepted runs (`on`/`off`; also on the MEMORIA page) | `on` |
| `AEHUB_EMBEDDER` / `AEHUB_EMBEDDING_MODEL` | Memory embedder: `sentence-transformers` (local model) or `hash` (no download, weaker recall); also on the MEMORIA page | `sentence-transformers` / `all-MiniLM-L6-v2` |
| `AEHUB_MEMORY_MIN_SIMILARITY` | Minimum cosine similarity for a vector match in hybrid retrieval; also on the MEMORIA page | `0.25` |
| `AEHUB_ALLOWED_DIRS` | Folders that filesystem tools may touch (`os.pathsep`-separated); the first one is the working folder searched by `search_documents` | `./workspace` |
| `AEHUB_DOCUMENTS_MAX_FILE_MB` | Files larger than this are listed in the document index with an error and are not searched (0.1–200; also on the DOCUMENTI page) | `5` |
| `AEHUB_MCP_ALLOWED_SERVERS` | Comma-separated MCP server URLs the bridge may connect to; also editable on the STRUMENTI page | none (no MCP server) |
| `AEHUB_DISABLED_TOOLS` | Comma-separated tools the agent can neither see nor call; set by the switches on the STRUMENTI page | none |
| `FRONTEND_URL` / `AEHUB_ALLOWED_ORIGINS` | Browser origins allowed by CORS and the WebSocket; any other origin cannot send POST, PUT, PATCH or DELETE | `http://localhost:3000` |
| `AEHUB_ALLOWED_HOSTS` | Extra host names the API answers to (comma-separated), besides `localhost`, `127.0.0.1` and `[::1]`; needed when the API is served under another name, e.g. on the LAN | none |
| `AEHUB_HOST` | Bind address of `python main.py` | `127.0.0.1` |
| `AEHUB_EVENT_BUS` | `memory` keeps live events and the cache inside the process, without Redis (the desktop app; also `REDIS_URL=memory://`) | Redis |
| `AEHUB_FRONTEND_DIR` | Static frontend export the API serves from its own origin (the desktop app) | none |
| `AEHUB_DATA_DIR` / `AEHUB_PG_BIN` | Desktop app: folder of the database cluster and logs; folder with `initdb` and `pg_ctl` | `%LOCALAPPDATA%\AEHub` / bundled |
| `AEHUB_VOICE` | `local` (faster-whisper + Piper on this machine) or `off` | `local` |
| `AEHUB_STT_MODEL` / `AEHUB_STT_LANGUAGE` / `AEHUB_TTS_VOICE` | Whisper model, spoken language (`auto` to detect), Piper voice; also editable on the VOCE page | `base` / `it` / `it_IT-paola-medium` |
| `AEHUB_TTS_ENGINE` | `piper` (on this machine) or `elevenlabs` (the reply text goes to ElevenLabs, ADR-024); also editable on the VOCE page | `piper` |
| `AEHUB_ELEVENLABS_VOICE` / `AEHUB_ELEVENLABS_MODEL` | ElevenLabs voice ID and model | none / `eleven_flash_v2_5` |
| `AEHUB_VOICE_MODELS_DIR` | Where the speech models are downloaded on first use | `~/.cache/aehub/voice` |
| `AEHUB_HOME_DEVICES` | JSON file of the home devices, outside the working folder (see Home devices) | none (no home tools) |
| `AEHUB_MQTT_URL` / `AEHUB_MQTT_USERNAME` | Home MQTT broker (`mqtt://host:1883`, `mqtts://host:8883`) and user | none |
| `AEHUB_TOOL_SELECTION` / `AEHUB_TOOL_TOP_K` | Skill index: show each run only the tools its task names (`AEHUB_TOOL_TOP_K` 1–50); also editable on the STRUMENTI page | `on` / `6` |
| `AEHUB_SKILL_INDEX_PATH` | The skill index's own SQLite file | `~/.cache/aehub/skill_index.sqlite3` |

### Security notes

The backend refuses to start without `AEHUB_SECRET_KEY` (or with the old placeholder value). The launcher creates a random one in the keyring.

The PostgreSQL password is the one secret kept in a file (the root `.env`, ignored by Git), because the database container reads it too. All ports are bound to `127.0.0.1`.

The API answers only to loopback host names (DNS rebinding) and refuses state-changing requests from pages of other origins. For cookies every `localhost` port is the same site, so a page on another local port would otherwise send requests with the owner's session.

In the desktop app the database password is generated on first start and kept in the OS keyring, and Postgres listens only on `127.0.0.1` without a Unix socket.

---

# Usage

## Text agent request

The current orchestration API exposes:

```text
POST /api/orchestrator/ask
```

The endpoint expects multipart form data.

Example:

Every `/api/` route (except `/api/auth/`) needs the HttpOnly session cookie that `/api/auth/login` sets; it is the only credential (no `Authorization` header, no `X-Session-ID`).

```bash
curl -c cookies.txt -X POST "http://localhost:3002/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"key": "replace_with_your_AEHUB_SECRET_KEY"}'

curl -b cookies.txt -X POST "http://localhost:3002/api/orchestrator/ask" \
  -F "text=Search the web for the latest information about LangGraph and summarize it."
```

The agent can decide to use the web-search skill when appropriate.

## Asking about your documents

Put text, Markdown or PDF files in the working folder (`./workspace`, or the folder chosen with `setup`) and ask about them:

```text
When should I water the tomatoes? Check my notes.
```

The agent calls `search_documents`, which brings the index up to date (only new or changed files are read, deleted ones leave the index) and returns the best excerpts. Every fact in the answer carries its source: `[doc: notes/garden.md#L3-9]` for lines of a text file, `[doc: report.pdf#p3]` for a PDF page.

* Hidden files and folders are skipped, and so is any link that leads outside the working folder.
* Documents are treated as untrusted data: after a search, any HIGH-risk action needs your approval, even if a document tells the agent otherwise. The same holds in a later session that recalls that conversation.
* Document excerpts are never stored as preferences or rules, and they are not recalled automatically: only `search_documents` reads them.
* `GET /api/documents` lists the indexed files (with errors such as an encrypted PDF); `POST /api/documents/sync` re-indexes now, which is useful after copying many files at once. Both need file access (the admin role).

## Python client example

```python
import httpx

API_URL = "http://localhost:3002"
SECRET_KEY = "replace_with_your_AEHUB_SECRET_KEY"

with httpx.Client(base_url=API_URL, timeout=120) as client:
    # The login sets the session cookie; the client sends it from now on.
    client.post("/api/auth/login", json={"key": SECRET_KEY}).raise_for_status()

    response = client.post(
        "/api/orchestrator/ask",
        data={"text": "Search the web for the latest information about LangGraph."},
    )

response.raise_for_status()
print(response.json())
```

## Voice

Voice runs on this machine: faster-whisper turns speech into text and Piper speaks the reply, both on the CPU. No audio leaves the computer, and voice works offline once the models are downloaded (about 150 MB and 60 MB, on first use).

- The microphone button of the Nucleo (or the space bar) records and sends the audio to `/api/orchestrator/listen`; the WebSocket accepts the same audio. The sphere follows the real level of your voice and of the reply.
- The transcript is your instruction, checked like a typed one.
- **A HIGH-risk action asked by voice always waits for your approval on screen**, also in a clean run: the microphone also hears a TV or another person.
- `AEHUB_VOICE=off` turns voice off. Without the speech engine the written reply still arrives.
- **The VOCE page** of the Control Plane (F3, ADR-024) changes the recognition model and language, the voice and its engine without a restart, plays a preview and lists the models already downloaded with their size.
- **ElevenLabs (optional, off by default).** Choose it on the VOCE page and add `ELEVENLABS_API_KEY` (the desktop app saves it in the OS keyring; with Docker use `python scripts/aehub.py setup`). The text of the replies then goes to ElevenLabs; your voice never does. Piper speaks whenever ElevenLabs cannot: no key or voice, an error, or a reply over 2,500 characters.
- A run asked by voice answers by voice also when it resumes after an approval.

## Home devices

The agent controls lights and locks through an MQTT broker on your network (Mosquitto, Zigbee2MQTT, Tasmota).

1. Copy `config/home.example.json` to `config/home.json` and list your devices: id, name, type (`light` or `lock`), MQTT topic and format (`zigbee2mqtt`, the default, or `tasmota` for lights).
2. In `backend/.env` set `AEHUB_HOME_DEVICES=/app/config/home.json` and `AEHUB_MQTT_URL`, plus `AEHUB_MQTT_USERNAME` when the broker needs a user. The password goes in the keyring (`python scripts/aehub.py setup`). In the desktop app, `home.json` goes next to the database in `%LOCALAPPDATA%\AEHub`.
3. Restart. The configuration check reports an invalid file or a missing broker.

Each action is its own tool with its own risk: listing devices, a light, and locking a door are LOW; **unlocking a door is HIGH and always waits for approval**. The agent names a device you declared, never a topic or a host. The device file must stay outside the agent's working folder: there the agent's file tools could change it.

## Which tools a run sees

At the start of every run the skill index, a SQLite database of its own, picks from your task alone the tools it names (at most `AEHUB_TOOL_TOP_K`). The model is shown only those, and a call to any other tool is refused, so an instruction hidden in a web page or a document cannot reach a tool your task never asked for. When no word of the task matches a tool, every tool is shown, as before. On the evaluation suite this cut the mean cost per case by about a third.

## Slash commands

`/stop` is the only command (`/clear`, `/precise`, `/creative`, `/deep` and `/fast` never had an effect and were removed in M15). To stop a running agent, use **Stop** on the Runs page.

---

# Example

## End-to-end web research

### Input

```text
Find recent information about LangGraph and give me a concise summary.
```

### Execution

The runtime follows approximately:

```text
User Request
    ↓
Prompt Injection Filter
    ↓
A.U.R.O.R.A.
    ↓
LLM
    ↓
Need external information?
    ↓
Web Search Tool
    ↓
DuckDuckGo Results
    ↓
Observation returned to Agent
    ↓
LLM synthesizes results
    ↓
Final answer
```

### Expected output shape

The exact response depends on the LLM and the search results, but conceptually:

```text
LangGraph is an orchestration framework for building stateful,
multi-step agent workflows. Recent developments include improvements
around graph-based execution, persistence, and tool-driven agent loops.
```

The important property is that the model does not need to rely exclusively on its static context when the web-search tool is selected.

---

# Agents and Tools

## Agent definition

The main runtime is defined in:

```text
backend/app/runtime/aurora.py
```

The graph contains an agent node and, when tools are registered, a tool execution node.

Conceptually:

```python
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        END: END,
    },
)

workflow.add_edge("tools", "agent")
```

This creates a reusable tool-calling loop.

## Skill-based tool registration

Skills implement the `BaseSkill` abstraction.

Example:

```python
from typing import Callable, List

from langchain_core.tools import tool

from .base import BaseSkill, SkillMetadata


@tool
def calculate_square(number: int) -> int:
    """Return the square of an integer."""
    return number * number


class CalculatorSkill(BaseSkill):
    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="calculator",
            description="Provides basic mathematical operations.",
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        return [calculate_square]


def get_skill() -> BaseSkill:
    return CalculatorSkill()
```

The registry dynamically discovers modules exposing:

```python
get_skill()
```

and aggregates their tools.

## Tool calling lifecycle

```text
Skill
  ↓
Tool registration
  ↓
Skill Registry
  ↓
LangGraph
  ↓
LLM binds available tools
  ↓
LLM emits tool call
  ↓
ToolNode executes function
  ↓
Result returned to LLM
```

## Tool metadata and risk levels

Tools can expose metadata describing:

* name;
* description;
* risk level;
* approval requirements;
* required permissions.

The current risk model includes:

```text
LOW
MEDIUM
HIGH
```

This provides an architectural foundation for policy enforcement and human approval.

---

# Memory and RAG

## Memory architecture

ÆHub distinguishes several memory layers.

### Working memory

Handled through LangGraph state.

It represents the active execution context, including the current message sequence.

### Conversational memory

LangGraph checkpoints are persisted through PostgreSQL using `AsyncPostgresSaver`.

This allows a session to retain graph state across executions.

### Semantic memory

Persistent facts about the user or environment.

Example:

```text
User prefers concise responses.
```

### Episodic memory

Records significant tasks and outcomes.

Example:

```text
Task: Research topic X
Outcome: Completed successfully
```

### Procedural memory

Stores preferences or operational rules that should influence future behavior.

Example:

```text
Always use concise answers unless explicitly asked for detail.
```

## Context Manager and memory retrieval

Every model request of the native engine is assembled by the Context Manager
(`backend/app/agent_engine/context.py`) inside one token budget
(`AEHUB_CONTEXT_BUDGET`, ~88k by default):

| Level | Content |
| --- | --- |
| L0 System | system prompt and tool schemas |
| L1 Task | the goal of the run and the checker feedback |
| L2 Project | the user's trusted preferences and rules |
| L3 Working set | the State Snapshot (Goal / Completed / Failed / Pending) of older tool calls |
| L4 Recent | the latest tool calls and results |
| L5 Historical | memories from earlier sessions, recalled by hybrid retrieval |

Every `AEHUB_SNAPSHOT_EVERY` tool calls the older calls leave L4 and are
summarized in the snapshot. The snapshot is deterministic (no model call) and
never quotes output of untrusted tools. The durable run state keeps every
observation; only the model input is compacted.

## RAG

Long-term memory lives in the `memory_chunks` table
(`backend/app/memory/store.py`), scoped to the workspace and the user, not
to the login session, so a fact saved in one session is recalled in the next.

- Indexing: memory tools (`save_semantic_memory`, `save_procedural_memory`,
  `save_user_preference`) and every run accepted by the Critic, chunked and
  embedded.
- Retrieval: PostgreSQL full-text search (GIN index on `tsvector`) and
  pgvector cosine distance, fused with Reciprocal Rank Fusion, packed into the
  L5 budget at the start of each run.
- Poisoning: anything written while untrusted content (web, files, MCP) is in
  the run context is stored as untrusted. It never becomes a preference or
  rule (L2) and is recalled only inside an untrusted-data fence.
- Control: `GET /api/memory`, `POST /api/memory/preferences`,
  `DELETE /api/memory/{id}` let the user review, add and forget memories.

The legacy `AuroraMemoryManager` (session-scoped `vector_memory` table) is
still used by older workers.

## Current pattern

The implemented architecture is closest to:

**Supervisor → Specialized Worker**

The supervisor decides when deep research should be delegated instead of attempting to perform the complete task itself.

## Subagents

Subagents are created as specialized LangGraph graphs with:

* a role-specific system prompt;
* an optional tool set;
* independent execution state;
* a final result returned to the supervisor.

The current repository contains a reusable `SubagentFactory`.

## Future multi-agent patterns

The architecture can evolve toward:

### Planner / Worker

```text
Planner
 ├── Worker A
 ├── Worker B
 └── Worker C
       ↓
    Aggregator
```

### Debate

```text
Agent A ──┐
          ├── Critic ──> Final Agent
Agent B ──┘
```

### Peer-to-peer

```text
Agent A ↔ Agent B ↔ Agent C
```

These patterns should only be introduced when they provide measurable improvements in quality, reliability, or task decomposition.

---

# Observability and Evaluation

## Current observability

The application includes an internal EventBus (Redis Pub/Sub) and an SSE endpoint:

```text
GET /api/events                    events of the login session
GET /api/events?scope=workspace    run states and approvals of the whole workspace
```

The session stream carries agent logs and the live state of the session's runs. The workspace stream feeds the Control Plane (`/control-plane`): Approvals, Runs, the single-run view, Memory and Security re-read their data when a run changes state or an approval is requested or decided, instead of polling.

The agent runtime also emits diagnostic events when routing work through A.U.R.O.R.A.

## Logging

Current logging is primarily application-level logging through Python output and EventBus events.

For production deployments, structured logs should be preferred:

```json
{
  "timestamp": "2026-08-17T12:00:00Z",
  "session_id": "demo-session",
  "agent": "aurora",
  "event": "tool_call",
  "tool": "perform_web_search"
}
```

## Tracing

`langsmith` is included in the backend dependencies, making LangSmith a potential observability layer.

Full end-to-end production tracing should be treated as an explicit deployment concern rather than assumed to be enabled by the dependency alone.

Recommended trace fields include:

* request ID;
* session ID;
* graph node;
* tool name;
* model;
* token usage;
* latency;
* retry count;
* error category;
* final outcome.

## Evaluation

Agent evaluation should measure at least:

| Metric                  | Goal                                        |
| ----------------------- | ------------------------------------------- |
| Task success rate       | Does the agent complete the requested task? |
| Tool selection accuracy | Does it invoke the right capability?        |
| Hallucination rate      | Does it invent facts or actions?            |
| Latency                 | How long does each task take?               |
| Cost                    | How much does each task consume?            |
| Reliability             | How often does execution fail?              |
| Safety                  | Does the agent stay within permissions?     |

The repository currently does not contain a dedicated agent-evaluation suite, so this should be treated as an area for future hardening.

---

# Security

Agentic systems require stronger controls than ordinary CRUD applications because the LLM can influence real-world actions.

## API key management

Never hard-code:

* `OPENAI_API_KEY` / `OPENROUTER_API_KEY`;
* `AEHUB_SECRET_KEY`;
* database passwords;
* external service credentials.

Use:

* `.env` files locally;
* secret managers in production;
* environment-specific credentials;
* key rotation policies.

## Prompt injection

The repository includes a `PromptInjectionFilter` that blocks common instruction-override patterns before the prompt reaches the LLM.

This is useful as a first layer, but prompt filtering should never be considered a complete defense.

Production systems should combine:

```text
Input validation
+
Context isolation
+
Tool authorization
+
Output validation
+
Human approval
```

## Tool permissions

Tools are associated with risk metadata.

Examples:

```text
LOW    → informational actions
MEDIUM → controlled computation
HIGH   → shell or sensitive actions
```

High-risk tools should require explicit authorization.

## Data isolation

Sessions should remain isolated through:

```text
session_id
```

Memory and persisted state should always be scoped to the authenticated principal.

Do not use globally shared default sessions for production workloads.

## Rate limiting

Rate limiting should be added at the API gateway or application boundary.

Recommended controls include:

* per-user rate limits;
* per-IP limits;
* per-tool limits;
* LLM concurrency limits;
* exponential backoff.

## Sandboxing

The repository includes sandbox tooling for:

* Python execution;
* shell execution.

The shell tool is classified as high risk and marked as requiring approval.

Sandbox execution should remain isolated, resource-limited, and network-restricted.

## Human approval

Sensitive operations should move through an approval boundary:

```text
Agent
  ↓
Risk Evaluation
  ↓
Requires Approval?
 ├── No → Execute
 └── Yes
       ↓
   Human Approval
       ↓
     Execute
```

The current repository defines approval-related metadata, but a complete user-facing approval workflow is still an area for further implementation.

---

# Performance and Scalability

## Caching

Use caching for:

* repeated web searches;
* static external responses;
* expensive model operations where deterministic replay is safe;
* derived application data.

Redis is already provisioned and can serve as the foundation for distributed caching.

## Parallel execution

Independent tasks should be executed concurrently where safe.

For example:

```text
                    ┌── Search A ──┐
Agent → Planner ────┼── Search B ──┼──→ Aggregator
                    └── Search C ──┘
```

Avoid parallel execution for actions with ordering or shared-state dependencies.

## Model selection

Not every task needs the largest available model.

A production routing policy can use:

```text
Simple classification       → lightweight model
Normal task execution       → standard model
Complex planning/research   → stronger model
Specialized worker task     → deterministic model
```

The current implementation uses Groq-hosted `llama3-70b-8192` for the main agent and a lower-temperature configuration for subagents.

## Cost optimization

Track:

* input tokens;
* output tokens;
* tool calls;
* model latency;
* retries;
* external API usage.

Reduce cost through:

* prompt minimization;
* context trimming;
* memory summarization;
* caching;
* smaller models for deterministic subtasks;
* bounded agent loops.

## Queues and workers

Long-running workloads should move outside the request-response lifecycle.

Today the agent engine runs inside the backend process and keeps durable run state in PostgreSQL; the Celery worker and the proactive scheduler were removed in M10 (ADR-019).

A scalable deployment can evolve toward:

```text
API
 ↓
Queue
 ↓
Worker Pool
 ├── Agent Worker
 ├── Research Worker
 ├── Automation Worker
 └── Evaluation Worker
```

## Horizontal scaling

Stateless API replicas can be scaled horizontally when shared state is externalized to:

* PostgreSQL;
* Redis;
* object storage;
* external observability systems.

---

# Roadmap

## Implemented

* [x] FastAPI backend
* [x] Next.js frontend
* [x] LangGraph-based A.U.R.O.R.A. runtime
* [x] Groq LLM integration
* [x] Dynamic skill registry
* [x] Tool calling
* [x] PostgreSQL-backed agent checkpoints
* [x] Semantic memory
* [x] Procedural memory
* [x] Episodic memory foundation
* [x] Web-search skill
* [x] Supervisor skill
* [x] Research subagent
* [x] Sandbox execution skill
* [x] Prompt-injection filter
* [x] Risk metadata for tools
* [x] EventBus and SSE streaming
* [x] Docker Compose environment
* [x] MCP bridge architecture foundation
* [x] Voice input/output pipeline

## Next (Now 100% Implemented)

* [x] Production-grade human approval workflow (approvals API, M2)
* [x] Persistent RBAC instead of session-based role placeholders
* [x] Dedicated vector database and RAG pipeline (pgvector)
* [ ] Citation-aware answers over the user's documents (M13)
* [x] Distributed tracing (OpenTelemetry)
* [x] Agent evaluation benchmark suite
* [x] Tool execution policy engine (ToolGateway)
* [x] Better model routing and fallback policies (ModelRouter)
* [x] API rate limiting
* [x] CI/CD pipeline (GitHub Actions)
* [x] Comprehensive unit and integration test coverage
* [x] Production secret management
* [x] Hardened sandbox isolation
* [ ] MCP client (the bridge has an allowlist and untrusted output, the connection is a stub; after V1)
* [x] Multi-agent orchestration patterns beyond supervisor/researcher
* [x] Production deployment documentation (ADRs)

---

# Contributing

Contributions are welcome.

## Development workflow

Create a feature branch from `main`:

```bash
git checkout main
git pull origin main

git checkout -b feature/<short-description>
```

Use focused branches such as:

```text
feature/rag-retrieval
feature/tool-permissions
fix/session-isolation
docs/agent-architecture
```

## Pull requests

A good pull request should include:

* a clear title;
* a concise explanation of the problem;
* implementation details;
* tests or validation steps;
* security considerations when tools or agent capabilities change;
* documentation updates when public behavior changes.

## Code quality

Backend code uses Ruff for linting and formatting.

Run:

```bash
ruff check .
ruff format .
```

Frontend code uses ESLint and Prettier.

Run:

```bash
npm run lint
npm run format
```

Avoid unrelated refactors in feature pull requests.

---

# Testing

Run the backend tests and the evaluation gate locally:

```bash
cd backend && python -m pytest ../tests -q && cd ..
make eval
```

## Unit & Integration Tests

The test infrastructure is located in `tests/` and heavily relies on `pytest`.
It programmatically covers:
* **Security Middleware:** SSRF, Path Traversal, and Secret Redaction.
* **Agent engine:** tool loop, human approval, guardrails, budget and limits, routing and failover, Context Manager and memory.
* **API surface:** the exact list of HTTP and WebSocket routes (`tests/security/test_api_surface.py`).

The frontend has component and hook tests (Vitest, Testing Library, jsdom) in `frontend/tests/`:

```bash
cd frontend && npm test && npm run lint
```

## Agent evaluations

`evals/run_evals.py` runs the cases in `backend/app/evaluation/dataset.json` through the real agent engine (planner loop, Tool Gateway, guardrails, approvals, Critic, Context Manager, memory). By default the model is scripted and the tools are deterministic, so the suite runs offline in seconds and costs nothing. `--live` uses the configured models instead.

The dataset covers successful tasks, retries after tool failures, tool selection, hallucination (answers must be grounded in tool output), human approval of HIGH-risk tools, prompt injection and secret leaks, cross-session memory, long context (50 tool calls under budget) and budget limits.

Each run reports the metrics of the spec (6.5): `success_rate`, `tool_accuracy`, `hallucination_rate`, `reliability`, `security_pass_rate`, `mean_cost` and latency. The release gate fails when:

* any security case fails (`security_pass_rate` must be 100%);
* any other metric is worse than `evals/baseline.json`, or mean cost grows by more than 10%.

```bash
make eval            # check against evals/baseline.json
make eval-baseline   # re-record the baseline after an intended change
```

CI runs the same gate on every push and pull request and uploads `eval-report.json`. It also runs `pip-audit`, `bandit`, Trivy and TruffleHog, checks the Compose file and builds both images. Third-party actions are pinned to commit SHAs.

---

# License

No open-source license is currently declared in the repository metadata.

```text
[LICENSE]
```

Until a license is explicitly added to the repository, reuse, modification, and redistribution rights should not be assumed.

---

# Acknowledgements

ÆHub is built on top of a number of open-source technologies and external services, including:

* [Python](https://www.python.org/)
* [FastAPI](https://fastapi.tiangolo.com/)
* [Next.js](https://nextjs.org/)
* [React](https://react.dev/)
* [LangChain](https://www.langchain.com/)
* [LangGraph](https://www.langchain.com/langgraph)
* [Groq](https://groq.com/)
* [Llama](https://www.llama.com/)
* [PostgreSQL](https://www.postgresql.org/)
* [Redis](https://redis.io/)
* [Playwright](https://playwright.dev/)
* [DuckDuckGo Search](https://duckduckgo.com/)
* [MCP](https://modelcontextprotocol.io/)
* [LangSmith](https://smith.langchain.com/)
* [Docker](https://www.docker.com/)

---

## Project Status

The architecture has successfully transitioned from an experimental project to a fully production-ready, zero-trust, durable execution platform. 

All core architectural gates—including Security (SSRF/Traversal defense), Durable Execution (PostgreSQL run state), Distributed Testing (Pytest Suite), and CI/CD operations—have been strictly enforced.

---

**© 2026 Samuele (AeSoul0). All rights reserved.**
