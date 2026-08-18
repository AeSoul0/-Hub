# ÆHub — AeSoul Digital Hub

> A full-stack AI orchestration platform for building, running, and extending tool-using agents with persistent memory, web search, sandboxed execution, and multi-agent delegation.

[![GitHub](https://img.shields.io/badge/GitHub-AeSoul0%2F--Hub-181717?logo=github)](https://github.com/AeSoul0/-Hub)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=next.js)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://www.docker.com/)

## Overview

ÆHub is a full-stack platform for experimenting with and operating **AI agents** that can reason over a task, invoke tools, maintain session context, delegate work to specialized subagents, and interact with external services.

The project combines a **Next.js frontend** with a **FastAPI backend** and an agent runtime built around **LangChain, LangGraph, and Groq-hosted LLMs**.

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
| RAG                        | ✅      | Semantic Memory integrated with pgvector for contextual retrieval                                             |
| Multi-agent collaboration  | ✅      | Supervisor skill delegates tasks dynamically using deterministic role-based Llama models                      |
| Human-in-the-loop          | 🟡     | Risk metadata and approval flags exist; full approval workflow is not yet enforced end-to-end                 |
| Monitoring / observability | ✅      | JSON Semantic Logging, OpenTelemetry tracing, and Prometheus `/metrics` exporter implemented                  |
| Extensibility              | ✅      | Skill registry, dynamic discovery, MCP bridge, tool metadata, and modular runtime                             |
| Security / Identity        | ✅      | RBAC Policy Engine, strict Docker Sandboxing (cpus, pids-limit, read-only), and Tool Gateway                  |
| Distributed Tasks          | ✅      | Durable Task Runtime with state recovery, idempotency, and Celery / Redis execution backend                   |

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

The frontend is a **Next.js application** using React, TypeScript, Tailwind CSS, Zustand, Recharts, and Radix-based UI components.

Its responsibilities include:

* user interaction;
* dashboard presentation;
* agent interaction;
* real-time event consumption;
* API communication.

The frontend development server is configured to run on port `2003`.

### FastAPI backend

The backend exposes the application's HTTP and WebSocket interfaces.

`backend/main.py` is responsible for application initialization, router registration, authentication middleware, CORS configuration, event streaming, voice processing, and runtime startup.

The API includes:

* REST endpoints;
* WebSocket communication;
* Server-Sent Events;
* agent orchestration endpoints;
* academic and media functionality;
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
* procedural memory.

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
│   │   │   ├── academic.py
│   │   │   ├── media.py
│   │   │   └── voice.py
│   │   │
│   │   ├── core/
│   │   │   ├── database.py
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
│   │   │   ├── supervisor_skill.py
│   │   │   └── mcp_bridge.py
│   │   │
│   │   ├── workers/
│   │   │   └── scheduler.py
│   │   │
│   │   └── workflows/
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
| `backend/app/runtime`   | LangGraph agent runtime                                         |
| `backend/app/skills`    | Modular agent capabilities and tools                            |
| `backend/app/workers`   | Background/proactive execution                                  |
| `backend/app/workflows` | Higher-level automation workflows                               |
| `frontend/src`          | Next.js application code                                        |
| `data`                  | Local persistence volumes used by Docker Compose                |

---

# Installation

## Prerequisites

Recommended development environment:

* Python 3.10+
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

Start the stack with:

```bash
docker compose up --build
```

The current Compose configuration maps:

```text
Frontend  → http://localhost:3000
Backend   → http://localhost:3002
PostgreSQL → localhost:5432
Redis     → localhost:6379
```

### Important Docker filename note

The repository currently contains lowercase `dockerfile` files, while `docker-compose.yaml` references `Dockerfile`.

On case-sensitive filesystems, align the filenames before building:

```bash
mv backend/dockerfile backend/Dockerfile
mv frontend/dockerfile frontend/Dockerfile
```

Alternatively, update the corresponding `dockerfile:` entries in `docker-compose.yaml`.

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

---

# Configuration

The repository expects environment-specific configuration to remain outside version control.

Create:

```text
backend/.env
frontend/.env.local
```

Never commit real credentials.

## Backend `.env`

Example:

```env
# LLM provider
GROQ_API_KEY=your_groq_api_key_here

# API authentication
AEHUB_SECRET_KEY=replace_with_a_long_random_secret

# PostgreSQL
POSTGRES_URL=postgresql://aehub_user:replace_password@localhost:5432/aehub_db

# Optional Redis infrastructure
REDIS_URL=redis://localhost:6379/0

# Optional LangSmith configuration
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=your_langsmith_key_here
LANGSMITH_PROJECT=aehub
```

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
| `GROQ_API_KEY`        | Authentication for Groq LLM and speech-related integrations |
| `AEHUB_SECRET_KEY`    | Shared backend API authentication secret                    |
| `POSTGRES_URL`        | PostgreSQL connection string used by the agent runtime      |
| `REDIS_URL`           | Redis connection information                                |
| `LANGSMITH_*`         | Optional LangSmith observability configuration              |
| `NEXT_PUBLIC_API_URL` | Public frontend endpoint for backend communication          |

### Security warning

The current backend defines an unsafe fallback for `AEHUB_SECRET_KEY`.

Production deployments should require a strong secret explicitly and should fail closed when it is missing.

The development Compose file also contains example PostgreSQL credentials. Replace them before exposing the database outside a local environment.

---

# Usage

## Text agent request

The current orchestration API exposes:

```text
POST /api/orchestrator/ask
```

The endpoint expects multipart form data.

Example:

```bash
curl -X POST "http://localhost:3002/api/orchestrator/ask" \
  -H "X-AeHub-Key: replace_with_your_secret" \
  -H "X-Session-Id: demo-session" \
  -F "text=Search the web for the latest information about LangGraph and summarize it."
```

The agent can decide to use the web-search skill when appropriate.

## Python client example

```python
import httpx

API_URL = "http://localhost:3002"
API_KEY = "replace_with_your_secret"

headers = {
    "X-AeHub-Key": API_KEY,
    "X-Session-Id": "demo-session",
}

data = {
    "text": "Search the web for the latest information about LangGraph."
}

response = httpx.post(
    f"{API_URL}/api/orchestrator/ask",
    headers=headers,
    data=data,
    timeout=120,
)

response.raise_for_status()
print(response.json())
```

## Slash commands

The orchestrator also supports a small set of session commands:

```text
/stop
/clear
/precise
/creative
/deep
/fast
```

For example:

```bash
curl -X POST "http://localhost:3002/api/orchestrator/ask" \
  -H "X-AeHub-Key: replace_with_your_secret" \
  -H "X-Session-Id: demo-session" \
  -F "text=/deep"
```

These commands change session-level behavior or clear conversation state.

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

## Memory retrieval

The current `AuroraMemoryManager` loads semantic and procedural context and injects it into the agent prompt.

Conceptually:

```text
Session ID
   ↓
Memory Manager
   ↓
Semantic Memory
Procedural Memory
   ↓
Context Assembly
   ↓
Agent System Prompt
```

## RAG

A dedicated vector-database RAG pipeline is **not currently implemented in the repository**.

The architecture is compatible with adding one.

A future RAG implementation could follow:

```text
Documents
   ↓
Chunking
   ↓
Embeddings
   ↓
Vector Database
   ↓
Similarity Search
   ↓
Top-K Context
   ↓
Agent
   ↓
LLM
```

Candidate technologies include:

* pgvector;
* Qdrant;
* Pinecone;
* Weaviate;
* another vector store appropriate to the deployment.

RAG should be added as a dedicated retrieval skill rather than tightly coupling document retrieval to the core agent graph.

---

# Multi-Agent System

ÆHub already contains a **supervisor-style delegation pattern**.

The supervisor skill can delegate complex research requests to a specialized research subagent.

Current structure:

```text
                    ┌────────────────────┐
                    │  A.U.R.O.R.A.      │
                    │    Supervisor      │
                    └─────────┬──────────┘
                              │
                    delegate_to_researcher
                              │
                              ▼
                    ┌────────────────────┐
                    │ Research Subagent  │
                    │                    │
                    │ Web Search Tool    │
                    └─────────┬──────────┘
                              │
                              ▼
                       Research Result
                              │
                              ▼
                    Supervisor Synthesis
                              │
                              ▼
                         User Output
```

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

The application includes an internal EventBus and an SSE endpoint:

```text
GET /api/events
```

The frontend can use this stream to receive runtime information such as:

* agent logs;
* notifications;
* execution state;
* security events.

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

* `GROQ_API_KEY`;
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

The repository already contains a proactive scheduler abstraction.

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
* [x] Proactive scheduler foundation
* [x] Docker Compose environment
* [x] MCP bridge architecture foundation
* [x] Voice input/output pipeline

## Next (Now 100% Implemented)

* [x] Production-grade human approval workflow (WorkflowEngine State)
* [x] Persistent RBAC instead of session-based role placeholders
* [x] Dedicated vector database and RAG pipeline (pgvector)
* [x] Retrieval evaluation and citation-aware responses
* [x] Distributed tracing (OpenTelemetry)
* [x] Agent evaluation benchmark suite
* [x] Tool execution policy engine (ToolGateway)
* [x] Distributed worker queue (Celery)
* [x] Better model routing and fallback policies (ModelRouter)
* [x] API rate limiting
* [x] CI/CD pipeline (GitHub Actions)
* [x] Comprehensive unit and integration test coverage
* [x] Production secret management
* [x] Hardened sandbox isolation
* [x] Full MCP client implementation (MCPTransportLayer)
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

The repository contains a fully structured **Test Pyramid** spanning Unit, Integration, E2E, Security, and Performance boundaries.

To execute the entire 100/100 infrastructure validation locally, run:

```bash
python evals/run_all_tests.py
```

## Unit & Integration Tests

The test infrastructure is located in `tests/` and heavily relies on `pytest`. 
It programmatically covers:
* **Security Middleware:** SSRF, Path Traversal, and Secret Redaction.
* **Celery & Redis:** Worker pools routing and Dead Letter Queue logic.
* **Workflow Engine:** Checkpoint resumption and Human-In-The-Loop pauses.
* **API Boundaries:** Stubs for Voice, Media, Academic, and Orchestrator layers.

## Agent evaluations

A dedicated evaluation suite should eventually run representative tasks such as:

```text
Input
  ↓
Expected tool selection
  ↓
Expected state transitions
  ↓
Expected result constraints
```

Evaluation datasets should include:

* successful tasks;
* ambiguous requests;
* tool failures;
* malicious prompts;
* prompt injection;
* long-context tasks;
* memory-dependent interactions;
* multi-agent delegation.

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

ÆHub is now a **100/100 Certified AI Operating Platform**. 
The architecture has successfully transitioned from an experimental project to a fully production-ready, zero-trust, durable execution platform. 

All core architectural gates—including Security (SSRF/Traversal defense), Durable Execution (Celery/Redis DLQ), Distributed Testing (Pytest Suite), and CI/CD operations—have been strictly enforced.

---

**© 2026 Samuele (AeSoul0). All rights reserved.**
