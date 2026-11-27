# ÆHub — AeSoul Digital Hub

> A personal, local-first agent operating system: one owner, one machine, an agent that uses real tools under explicit rules — approvals, budgets, audit — with long-term memory, voice and home control.

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-Next.js%2016-000000?logo=next.js)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://www.docker.com/)

## Overview

ÆHub runs on your own computer, for one person. You give it a task by text or voice; its engine, **A.U.R.O.R.A.**, asks a model what to do, runs the tools the model proposes through one gateway, has an independent Critic check the answer, and shows every step live.

- **The model proposes, the engine decides.** Every tool call goes through the Tool Gateway: policy, guardrails, schema, idempotency, budget, approval and a hash-chained audit. HIGH-risk actions (a shell command, unlocking a door) wait for your approval.
- **Runs are durable.** A run waiting for approval, or cut by a crash, resumes with the same id from PostgreSQL, and a tool already executed does not run again.
- **Any model, per role.** Architect, Research, Critic, Fast Worker and Triage each have a chain of models with fallbacks. Providers: OpenAI, OpenRouter, a local server (Ollama, LM Studio), Groq, Anthropic and Google Gemini, through Pydantic AI (ADR-032). The Critic never uses the same model as a worker.
- **Limits you set.** Cost per run and per month, active time, failed tool calls, subagents and modified files; a stop button for one run or for all of them.
- **Memory and documents.** Facts, preferences and rules across sessions; search over the documents of your working folder, with cited sources. Content from the web, files or MCP is untrusted: it never becomes a rule, and after reading it every HIGH-risk action needs an approval.
- **Voice and home.** Speech recognition and synthesis run on this machine (faster-whisper, Piper); lights and locks through your MQTT broker.
- **Your files, where you say.** The agents list, find, read, write and move files in the working folder and in the folders you add on STRUMENTI; replacing or deleting a file waits for your approval. ÆHub's own files, hidden files (`.ssh`, `.env`) and AppData stay out of reach (ADR-036).
- **Answers as they are written.** In the Nucleo the answer appears while the model writes it, marked as a draft until the Critic accepts it; the accepted answer is then spoken sentence by sentence, the next one prepared while one plays (ADR-040).
- **Hands-free.** Choose a wake word on the VOCE page ("Hey Jarvis", "Alexa", "Hey Mycroft", or your own "Aurora" model): the Nucleo listens for it in the page, then records the command until you stop speaking. No audio is recorded or sent anywhere before the word (ADR-041).
- **A memory that follows the conversation.**
  - **Follow-ups:** every command sees the last turns of the conversation, so "and tomorrow?" knows what came before.
  - **Long conversations:** their oldest turns become one summary.
  - **Documents:** search with cited sources covers the working folder and the folders you give the agents.
  - **Italian:** a multilingual embedding model, better for Italian, can be chosen on MEMORIA (ADR-042).
- **Everyday commands at once.**
  - "Alza il volume", "pausa", "blocca lo schermo", "fai uno screenshot", "timer di 5 minuti" and "ricordami alle 18 di chiamare Marco" run without the model.
  - A reminder rings in the Nucleo and, with the page in the background, as a notification.
  - The agents can also search inside your text files and PDFs, and read PDFs (ADR-043).
- **Approvals that reach you.** A run that waits for you asks one short question ("May I delete old.txt? Yes or no."); a plain "yes" or "no", spoken or typed, decides it and Aurora answers in a word. A system notification and the tab title tell you when a request waits and ÆHub is not in front (ADR-037).
- **Instant commands.** "Open Spotify", "open the downloads folder", "accendi la luce della cucina": simple commands run at once through the Tool Gateway, without the model, in milliseconds. The apps are the ones you list in Settings → Apps; anything else goes to the engine (ADR-035).
- **An interface for everything.** The Nucleo (home) and the Control Plane cover every route and setting of the backend (`docs/frontend-coverage.md`). They are in English by default, or in Italian (Settings → Language, or ask Aurora); the voice keeps the language of the voice you choose, and a notice says when the two differ (ADR-034).

It is not a multi-user service: there is one owner, and every port listens on `127.0.0.1`.

The engine is described in [`docs/architecture/AEHUB_ENGINE_V1.md`](docs/architecture/AEHUB_ENGINE_V1.md), the decisions in [`docs/adr/`](docs/adr/), and the repository in [`docs/architecture/inventory.md`](docs/architecture/inventory.md).

---

# Architecture

```mermaid
flowchart TD
    User[You: browser, desktop window, voice]
    Frontend[Next.js: Nucleo and Control Plane]
    API[FastAPI API]
    Engine[A.U.R.O.R.A. engine<br/>worker, Critic, triage]
    Models[Pydantic AI<br/>OpenAI, OpenRouter, local,<br/>Groq, Anthropic, Gemini]
    Gateway[Tool Gateway<br/>policy, approvals, budget, audit]
    Tools[Skills and tools<br/>web, browser, sandbox, files,<br/>documents, memory, home, subagents]
    DB[(PostgreSQL + pgvector<br/>runs, approvals, audit,<br/>settings, memory, documents)]
    Bus[(Redis<br/>live events, cache,<br/>rate limits)]

    User --> Frontend
    Frontend -->|REST, SSE, WebSocket| API
    API --> Engine
    Engine -->|one request per turn| Models
    Models -->|proposed tool calls| Engine
    Engine --> Gateway
    Gateway --> Tools
    Engine --> DB
    Gateway --> DB
    Engine --> Bus
    Bus -->|SSE| Frontend
```

## Core components

### Frontend

The frontend is a **Next.js application** using React, TypeScript and Tailwind CSS. Fonts are bundled from npm, so it loads nothing from third parties.

- **The Nucleo** (`/`, ADR-022) is the home:
  - a dotted sphere in the centre reacts to what the engine does: model calls, tool calls, subagents as small moons, approvals in amber, the microphone, the spoken reply;
  - the conversation sits on the left and the engine's live events on the right; both panes grow from their top edge and can be hidden;
  - pending approvals are decided there;
  - the **RUN** tab of the right pane follows each run of the session (ADR-023): cost, active time, failed tool calls, written files and subagents against the per-run limits, live, with a stop button and the run's timeline; **FERMA TUTTO** in the top bar stops every run (a second click confirms) and **RIPRENDI** lifts the stop;
  - next to the command field a role can be chosen for the next commands (Architect, Research, Fast Worker, Triage); "auto" leaves it to the triage (ADR-029).
- **The Control Plane** (`/control-plane`) has runs, approvals, memory, documents, home, tools, skills, security, voice, settings, system and setup, all in the Nucleo's style; the history of the runs filters by text, status, period and subagents, and shows each subagent under its parent. A run's page lists its subagents, and its timeline shows each verdict of the Critic with the attempt and the correction it asked for (ADR-029).
- **Settings** (ADR-025) choose the LLM of each role (Architect, Research, Critic, Fast Worker, Triage) with its fallbacks, suggesting each provider's models (OpenRouter with prices), and refuse a Critic that shares a model with another role. They also hold keys, default models, the local server, prices, budget and limits, the approval window, the circuit breaker and the context budget, all applied without a restart.
- **Tools and skills** (ADR-026):
  - **STRUMENTI** lists every skill and tool with its risk, approval, network and file access, and whether it returns untrusted content. It switches tools off: a disabled tool is never shown to the agent and is refused if proposed. The page also sets the skill index, the allowed MCP servers and the risk of each MCP tool; it shows what each MCP server answered, with a button to reconnect, and the tools' folders, the API host names and the sandbox.
  - **SKILL** imports skills in the open `SKILL.md` format (Claude Code, Codex, OpenClaw) from an https link (a GitHub page is turned into its raw file) or a file. Only the text is imported, and the skill starts off. The page shows the whole text and flags patterns to check before it can be turned on: download-and-run commands, encoded blobs, instruction overrides, secrets, bundled files and links. The agent reads an enabled skill through the `use_skill` tool as untrusted content, so after reading it every high-risk action waits for an approval.
  - **SICUREZZA** shows the audit hash chain, the log (Control Plane changes included) filtered by decision and tool, and which entries returned untrusted content.
- **SISTEMA** (ADR-030), for the owner only:
  - the state of the database and the event bus, the app's version and uptime;
  - the RAM of ÆHub's processes (backend with voice, PostgreSQL, the browser's Chromium, the desktop window) and the local models in memory (voice and the memory's embedder);
  - whether a newer desktop version is published;
  - the startup parameters, read only, with no password shown;
  - flight recorder search and JSONL export;
  - the offline evals, run in a separate process (the release gate when `evals/baseline.json` is there);
  - rotating the access key (desktop app, keyring), which closes every other session;
  - the backend's recent warnings and errors;
  - links to the API's own pages: `/docs`, `/redoc`, `/openapi.json`, the Prometheus `/metrics` and the `/health` probe (they need no login and answer on the API's host).
  - **The run view** also lists the tools the skill index picked for the run.
- **Home** (ADR-028): the **CASA** page lists your devices with what ÆHub last sent and, on request, what the device says; it adds and edits devices, sets the MQTT broker and tests the connection.
- **Memory and documents** (ADR-027):
  - **MEMORIA** turns long-term memory on or off and sets the similarity threshold, the embedder and its model. After an embedder change it recomputes the old vectors.
  - On the same page you add facts, preferences and rules, search with the engine's hybrid retrieval, and filter by kind and trust. A memory can be edited in place, forgotten, or vouched for ("Mi fido", audited) when it was written from untrusted content. All untrusted memories can be forgotten at once.
  - **DOCUMENTI** shows the working folder and its index. It syncs, uploads a file into the folder, sets the size limit and searches the index.
  - **Citations** `[doc: file#lines]` in answers (Nucleo and run view) open the cited passage.
- **How much of the backend the interface controls** is tracked in `docs/frontend-coverage.md`: 100% since F10. Its index maps every route, setting, startup parameter and secret to the row that covers it, and `tests/security/test_frontend_coverage.py` fails when something new is missing.

The look is a deep-blue space theme with squircle corners. The visual reference is `docs/design/hud-prototype.html`.

The frontend development server is configured to run on port `2003`.

### FastAPI backend

`backend/main.py` builds the application: routers, the session check on every `/api/` route, the host and origin checks, rate limits, telemetry and, in the desktop app, the static frontend. The API speaks REST, Server-Sent Events (`/api/events`) and a WebSocket (`/ws/orchestrator`) for text and voice commands. The exact list of routes is in `tests/security/test_api_surface.py`.

### A.U.R.O.R.A. engine

**Autonomous Uplink & Real-time Operations Robotic Assistant** is the project's own execution loop (`backend/app/agent_engine/`), with no agent framework as the authority:

```text
task → triage picks the role
     → worker model: text and proposed tool calls
     → Tool Gateway: each call checked, approved if needed, run, audited
     → observations stored with the run → next turn
     → final answer → Critic (different model) → accepted, or feedback and retry
```

The input of every turn is rebuilt from the run's durable state, so a run can resume after an approval or a crash, or move to a fallback model, without repeating a tool call. Details in [`docs/architecture/AEHUB_ENGINE_V1.md`](docs/architecture/AEHUB_ENGINE_V1.md).

### Models

One adapter, `PydanticAIAdapter` (`backend/app/agent_engine/adapters/pydantic_ai_adapter.py`, ADR-032), makes exactly one model request per turn with `pydantic_ai.direct.model_request` and returns the text, the proposed tool calls, the token usage and the response id. Pydantic AI runs no tool: the loop stays A.U.R.O.R.A.'s.

| Provider | Model class | Key |
| --- | --- | --- |
| `openai` | OpenAI Responses API | `OPENAI_API_KEY` |
| `openrouter` | Chat Completions on OpenRouter | `OPENROUTER_API_KEY` |
| `local` | Chat Completions on an OpenAI-compatible server (`AEHUB_LOCAL_BASE_URL`) | none, or `AEHUB_LOCAL_API_KEY` |
| `groq` | Groq | `GROQ_API_KEY` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` |
| `google` | Gemini | `GEMINI_API_KEY` |

Each role has its chain of `provider:model` (Settings, or `AEHUB_MODEL_ROLES`). When a provider fails, a per-target circuit breaker moves the call to the next model of the chain. A provider appears in the role editor once its key is set. LiteLLM is not used.

### Skills and tools

Skills live in `backend/app/skills/` and expose plain Python functions with metadata: risk (LOW, MEDIUM, HIGH), approval, permissions, network and file access, and whether the output is untrusted. The registry loads every module with a `get_skill()`.

At the start of a run the skill index shows the model only the tools the task names (see [Which tools a run sees](#which-tools-a-run-sees)). Skills in the open `SKILL.md` format can be imported from the SKILL page; their text reaches the agent as untrusted content. The MCP client (ADR-033) connects only to the allowed servers, over Streamable HTTP. Each MCP tool is high risk and waits for your approval on every call until you lower its risk on STRUMENTI. Its output is always untrusted, and a server that needs a login gets its token from the keyring (`AEHUB_MCP_TOKENS`).

### Memory

Long-term memory (`backend/app/memory/store.py`, ADR-027) is scoped to the workspace and the user, not to the login session. Each run recalls what matches its task, by hybrid retrieval (full text and pgvector, fused with Reciprocal Rank Fusion), and runs accepted by the Critic are indexed. See [Memory and RAG](#memory-and-rag).

### PostgreSQL

PostgreSQL (with pgvector) holds everything durable: identities and sessions, runs and approvals, the hash-chained audit, settings, long-term memory with its vectors and full-text index, the document index and imported skills. The schema comes from the Alembic revisions in `backend/alembic/versions/`, applied at every start (see [Changing the schema](#changing-the-schema)).

### Redis

Redis carries the live events (the Nucleo and the Control Plane follow runs and approvals over SSE), the cache and the API's rate limits. It holds nothing durable. The desktop app runs without it: `AEHUB_EVENT_BUS=memory` (or `REDIS_URL=memory://`) keeps events, cache and limits inside the process.

### External services

Only what you turn on: the model providers you give a key to, DuckDuckGo for web search, the pages the browser tool opens, your MQTT broker, ElevenLabs if you choose it for voice, and GitHub Releases for desktop updates. The voice, the embedder and the database run on this machine.

---

# Project structure

```text
-Hub/
├── backend/
│   ├── main.py              # the FastAPI application
│   ├── desktop.py           # desktop sidecar: PostgreSQL and API on 127.0.0.1
│   ├── alembic/             # schema revisions (ADR-031)
│   └── app/
│       ├── agent_engine/    # A.U.R.O.R.A.: loop, Critic, routing, context, budget, adapter
│       ├── runtime/         # Tool Gateway and audit hash chain
│       ├── api/             # HTTP, SSE and WebSocket routes
│       ├── core/            # database, event bus, cache, security, settings, telemetry
│       ├── skills/          # tools: web, browser, sandbox, files, documents, memory, home, delegation
│       ├── memory/          # long-term memory
│       ├── documents/       # index of the working folder
│       ├── voice/ home/     # local voice; MQTT devices
│       ├── system/          # the SISTEMA page: status, logs, evals, recorder, updates
│       ├── evaluation/      # eval suite and release gate
│       └── domain/models/   # SQLAlchemy models
├── frontend/                # Next.js: src/app (pages), src/components, src/lib, tests
├── desktop/                 # Tauri shell of the Windows app (suspended)
├── tests/                   # backend tests (pytest)
├── evals/                   # run_evals.py and baseline.json
├── scripts/                 # aehub.py launcher, demo.py, check_headers.py
├── docs/                    # ADRs, architecture, configuration, coverage, design
├── config/                  # home.example.json
└── docker-compose.yaml
```

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

A key for at least one model provider (OpenAI, OpenRouter, Groq, Anthropic or Gemini), or a local OpenAI-compatible server such as Ollama.

### Clone the repository

```bash
git clone https://github.com/AeSoul0/-Hub.git
cd -Hub
```

## Try it in GitHub Codespaces (nothing to install)

ÆHub runs in a codespace, a Linux machine of GitHub opened from the browser, and you use it at a private HTTPS address that only your GitHub account can open (the microphone works there too).

1. On the repository page: **Code → Codespaces → Create codespace on main** (2 cores and 8 GB are enough).
2. When it is created, GitHub asks for the secrets listed in `.devcontainer/devcontainer.json`: put at least one model key (for example `OPENAI_API_KEY`). `AEHUB_SECRET_KEY` is the key you log in with; left empty, one is made for you. You can add or change them later in GitHub → Settings → Codespaces → Secrets, then restart the codespace.
3. The first start installs PostgreSQL with pgvector, the backend and the pages (a few minutes), then starts ÆHub and opens port 3002 in the browser. Log in with the key shown by:

```bash
bash scripts/codespace.sh key
```

The models of each role are chosen at start from the keys you gave, reading each provider's own model list (`scripts/codespace_models.py`):

- **Anthropic and Gemini:** Claude Opus plans, Gemini Pro researches, Claude Haiku and Gemini Flash-Lite do the quick jobs; the Critic is Gemini Flash, so another family checks Claude's answers, with Claude Sonnet as its fallback. Each role falls back on the other provider.
- **Only one of them:** the same split inside it (with Claude alone, Opus plans and Sonnet is the Critic; with Gemini alone, Flash is the Critic).
- **Only OpenRouter:** its free models that can call tools, the largest first, with a different one as the Critic. Free models have tight daily limits.
- **No key, or the `AEHUB_USE_OLLAMA=1` secret:** Ollama runs open models on the codespace's own CPU.
  - **Models:** Qwen 2.5 3B (`qwen2.5:3b`) does the work and Llama 3.2 3B (`llama3.2:3b`) is the Critic. Change them with `AEHUB_OLLAMA_MODEL` and `AEHUB_OLLAMA_CRITIC`.
  - **First start:** the models are downloaded once, about 4 GB.
  - **Cost and limits:** no account, no key, no daily limit.
  - **Speed:** slow. On 2 cores a command takes minutes, so the timeouts are raised. A 4-core machine (Code → Codespaces → ⋯ → Change machine type) is about twice as fast. Small models also use tools less reliably.

What you save in IMPOSTAZIONI wins over this choice.

Other commands: `bash scripts/codespace.sh start` (again, after a stop), `stop`, `status`, `logs`, and `build` after changing the frontend. Keys stay in the codespace's secrets, data in `~/.aehub`.

In a codespace ÆHub is on GitHub's machine, not on your PC: opening your apps and your folders, and the home devices on your network, do not reach your computer. Free accounts have a monthly allowance of codespace hours; stop the codespace when you are done.

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

Install packages (`requirements-dev.txt` adds pytest and Ruff, for the tests):

```bash
pip install -r requirements.txt -r requirements-dev.txt
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

> **Suspended.** Work on the desktop app is paused, and the CI builds no installer: the `desktop-windows` and `desktop-release` jobs run on a version tag only when the repository variable `DESKTOP_RELEASE` is `on`. What follows describes the app as it was last built; it stays the final goal.

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

# Configuration

Configuration has three homes:

* **Secrets** (provider API keys, the login key) — the OS keyring, through the launcher (see *First run*) or the desktop app. The backend reads them from its environment.
* **Settings** — model roles, prices, budget and run limits, voice, the tool settings (disabled tools, skill index, MCP servers), memory (on/off, similarity, embedder), the document size limit and the home MQTT broker. Edited in the Control Plane (**Settings**, `GET`/`PUT /api/settings`), stored in the `app_settings` table, applied from the next run without a restart. A setting never edited falls back to the environment variable of the same name, then to its default, so `backend/.env`, CI and tests keep working. Every change is validated as a whole (a Critic equal to a Worker is refused before it is saved) and recorded in the audit log as `settings.update`.
* **Infrastructure** — database, Redis, CORS, paths: environment only (`backend/.env`, root `.env` for Compose).

At startup the backend logs one line per configuration problem (`[CONFIG ERROR]`, `[CONFIG WARNING]`, …): Critic equal to a Worker, a provider without its key, models without a price, a run limit above the monthly budget, a missing working folder. The Settings page shows the same list. The API starts anyway, so the page can fix what it can; runs are refused while an error remains.

**Every variable, with its default, is in [`docs/configuration.md`](docs/configuration.md).**

## Backend `.env` (local development)

Example for running the backend outside Docker:

```env
POSTGRES_URL=postgresql://aehub_user:replace_password@localhost:5432/aehub_db
REDIS_URL=redis://localhost:6379/0
```

Outside Docker, put the keys in your shell environment (for example `AEHUB_SECRET_KEY`, `OPENAI_API_KEY`) rather than in this file. Voice needs no key: it runs on this machine (see Voice).

## Frontend `.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:3002
```

Do not expose private backend secrets through `NEXT_PUBLIC_*` variables.

## Security notes

The backend refuses to start without `AEHUB_SECRET_KEY` (or with the old placeholder value). The launcher creates a random one in the keyring.

The PostgreSQL password is the one secret kept in a file (the root `.env`, ignored by Git), because the database container reads it too. All ports are bound to `127.0.0.1`.

The API answers only to loopback host names (DNS rebinding) and refuses state-changing requests from pages of other origins. For cookies every `localhost` port is the same site, so a page on another local port would otherwise send requests with the owner's session.

**Pages open without login.** Every `/api/` route except `/api/auth/` needs the session cookie. The API's own pages do not: `/docs`, `/redoc` and `/openapi.json` (the description of the routes, no data), the Prometheus `/metrics` (the default counters of the Python process: memory, CPU, garbage collector) and the `/health` probe. This is deliberate for a single-user app on loopback: they answer only on `127.0.0.1` and loopback host names, and the SISTEMA page links them. If you ever publish the API under another name (`AEHUB_ALLOWED_HOSTS`), put a proxy with authentication in front of them.

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
  -F "text=Search the web for the latest news about pgvector and summarize it."
```

The reply comes back in the response, and the run shows live in the Nucleo and on the Runs page. The agent may use the web-search tool (DuckDuckGo); its results are untrusted content.

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
        data={"text": "Search the web for the latest news about pgvector."},
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
- **SpaceXAI (optional, off by default, ADR-038).** Choose it on the VOCE page, with the voice `eve` (energetic and cheerful, British accent) or `altair` (formal, elegant) and the language it reads in (`it`, `en`, `fr`, always explicit). Add `XAI_API_KEY` the same way as the ElevenLabs key. Pay per use: 15 $ per million characters, about 2.25 $ a month for 10 replies of 500 characters a day. Piper speaks whenever SpaceXAI cannot.
- A run asked by voice answers by voice also when it resumes after an approval.

## Home devices

The agent controls lights and locks through an MQTT broker on your network (Mosquitto, Zigbee2MQTT, Tasmota).

**From the CASA page** (no restart):

1. Set the broker address and, when it needs one, the user. The password goes in the keyring: the desktop app saves it from the page, otherwise use `python scripts/aehub.py setup` and restart. **Prova il collegamento** tests the connection.
2. Add your devices: name, type (`light` or `lock`), MQTT topic and format (`zigbee2mqtt`, the default, or `tasmota` for lights). The home tools appear on their own.

**From a file**, if you prefer:

1. Copy `config/home.example.json` to `config/home.json` and list your devices.
2. In `backend/.env` set `AEHUB_HOME_DEVICES=/app/config/home.json` and `AEHUB_MQTT_URL`, plus `AEHUB_MQTT_USERNAME` when the broker needs a user. In the desktop app, `home.json` goes next to the database in `%LOCALAPPDATA%\AEHub`.
3. Restart. The configuration check reports an invalid file or a missing broker.

Both lists work together and CASA shows the file's devices read only. An id may appear in only one of them.

Each action is its own tool with its own risk: listing devices, a light, and locking a door are LOW; **unlocking a door is HIGH**. From a run it always waits for approval. From CASA it needs a second click, recorded as the approval of that call. Commands sent from the page go through the same Tool Gateway as the agent's, so a tool turned off in STRUMENTI stays off.

The agent names a device you declared, never a topic or a host. The device file must stay outside the agent's working folder: there the agent's file tools could change it. Devices declared on the page live in the database, out of reach of those tools.

CASA shows the last command sent and says plainly that it is not proof the device obeyed. **Leggi lo stato** asks the device: Zigbee2MQTT topics ending in `/set` and Tasmota `cmnd/<name>/POWER` topics are supported.

## Which tools a run sees

At the start of every run the skill index, a SQLite database of its own, picks from your task alone the tools it names (at most `AEHUB_TOOL_TOP_K`). The model is shown only those, and a call to any other tool is refused, so an instruction hidden in a web page or a document cannot reach a tool your task never asked for. When no word of the task matches a tool, every tool is shown, as before. On the evaluation suite this cut the mean cost per case by about a third.

## Slash commands

`/stop` is the only command (`/clear`, `/precise`, `/creative`, `/deep` and `/fast` never had an effect and were removed in M15). To stop a running agent, use **Stop** on the Runs page.

---

# Memory and RAG

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
- Control: `GET /api/memory`, `POST /api/memory` (a fact, a preference or a
  rule), `PUT /api/memory/{id}` and `DELETE /api/memory/{id}` let the user
  review, add, edit, vouch for and forget memories.


## Subagents

A run delegates part of its task with the `delegate_task` tool (ADR-029). It goes through the Tool Gateway like any other tool and needs the `agent:invoke` permission, so an admin can delegate and a member cannot. The subagent:

* works with the role asked for (Architect, Research, Fast Worker or Triage), otherwise the one the triage picks, and is checked by the same independent Critic;
* gets at most the tools, permissions and budget of its parent: half of what the parent has left unless it asks for less; when the parent has no run cost cap (`AEHUB_RUN_MAX_COST=0`) it gets the budget it asks for, 1 USD by default;
* starts tainted when its parent has read untrusted content, and its answer is untrusted for the parent;
* cannot delegate again, and a run starts at most `AEHUB_RUN_MAX_SUBAGENTS` of them;
* costs its parent what it spent, even when it fails.

A subagent that needs an approval waits on its own: the parent is told and goes on.


---

# Observability

- **Live events.** Every step of a run (model calls, tool calls, approvals, subagents, the Critic's verdicts) is published on the event bus and streamed over SSE:

  ```text
  GET /api/events                    events of the login session
  GET /api/events?scope=workspace    run states and approvals of the whole workspace
  ```

  The Nucleo draws them live; the Control Plane pages re-read their data when a run changes state or an approval is requested or decided, instead of polling.
- **Run timeline.** `GET /api/runs/{id}/events` returns the recorded steps of one run, shown on its page.
- **Flight recorder.** Every event is also written to a JSONL file, searchable and exportable from the SISTEMA page.
- **Logs.** Structured JSON logs; the latest warnings and errors are on the SISTEMA page.
- **Tracing and metrics.** OpenTelemetry instruments FastAPI and SQLAlchemy (spans are printed on the console unless `AEHUB_TELEMETRY_CONSOLE=0`); Prometheus metrics are at `/metrics`.

---

# Security

The model is treated as untrusted; the engine and the Tool Gateway hold the authority. In short:

| Layer | What it does |
| --- | --- |
| Login | One owner, one access key (`AEHUB_SECRET_KEY`); an HttpOnly session cookie is the only credential. The key can be rotated from SISTEMA, which closes every other session. |
| Network | Every port on `127.0.0.1`; loopback host names only; state-changing requests only from the frontend's origin; rate limits per user (API, model calls, uploads). |
| Tool Gateway | Policy, argument guardrails (SSRF, paths, dangerous commands), schema, idempotency, budget, approval and audit before every call; secrets redacted from the output. |
| Approvals | HIGH-risk calls wait for the owner, in the Nucleo or on the Approvals page; undecided ones are denied after `AEHUB_APPROVAL_TTL_SECONDS`. After untrusted content, and for voice commands, every HIGH-risk call needs one. |
| Untrusted content | Web pages, files, MCP output and imported skills reach the model inside an `<untrusted_tool_output>` fence. Memories written after reading them are untrusted and never become preferences or rules. |
| Guardrails | Prompt-injection patterns in user text are refused; answers have secrets removed. CI runs a prompt-injection gate. |
| Sandbox | Python and shell run in Docker with no network, a read-only root, a memory, CPU and process limit, and no capabilities. |
| Audit | A hash chain in PostgreSQL of every tool call and every Control Plane change; the SICUREZZA page verifies it. |
| Secrets | In the OS keyring, never in the database or in logs; the interface writes keys but never shows them again. |

The threat model is in [`docs/security/threat-model.md`](docs/security/threat-model.md).

---

# Contributing

ÆHub is a personal project; changes go through pull requests on `main`, one per milestone, merged by hand when CI is green.

## Changing the schema

Since D1 (ADR-031) Alembic is the only source of the schema. At every start the API runs `alembic upgrade head` (Docker, `make demo` and the desktop app alike), so an update keeps memory, runs and audit. A database built before D1 by the old `create_all` is recognised, gets the tables it lacks and is marked at the baseline, without losing a row.

Every change to a model in `backend/app/domain/models/` is a new revision; no more separate tables to get around `create_all`:

```bash
cd backend
alembic revision --autogenerate -m "memory: add the expiry date"
```

Read the generated file before committing it: autogenerate does not see everything (data moves, expression indexes, extensions). Then check that the models and the revisions agree:

```bash
alembic upgrade head
alembic check
```

All three commands use `POSTGRES_URL`. In CI, `tests/database/test_migrations.py` builds a database from scratch and one with the old `create_all`, and fails when a model changed without a revision.

## Code quality

Backend:

```bash
cd backend
ruff check .
```

Ruff runs with `BLE001` (R1): a blind `except Exception` needs a reason in its `noqa` comment and, unless it re-raises or reports the error, a log line.

Frontend:

```bash
cd frontend
npm run lint
npm run format
```

Every source file starts with an `@file <path>` / `@description …` header, checked in CI:

```bash
python scripts/check_headers.py
```

---

# Testing

Run the backend tests and the evaluation gate locally:

```bash
cd backend && python -m pytest ../tests -q && cd ..
make eval
```

## Unit and integration tests

The backend tests are in `tests/` (pytest; most need PostgreSQL with pgvector at `POSTGRES_URL`). They cover:
* **Agent engine:** tool loop, human approval and resume, guardrails, budget and limits, routing and failover, the Pydantic AI adapter, Context Manager and memory.
* **Security:** SSRF, path traversal, secret redaction, the sandbox, the session and origin checks.
* **API surface:** the exact list of HTTP and WebSocket routes (`tests/security/test_api_surface.py`).
* **Frontend and backend agree:** every address the frontend calls is a real route with the right method (`tests/security/test_frontend_api_routes.py`), and every route, setting and variable has its row in `docs/frontend-coverage.md` (`tests/security/test_frontend_coverage.py`).
* **Database:** the Alembic revisions build the schema from scratch and upgrade an old database (`tests/database/`).
* **Desktop:** the sidecar and, with `AEHUB_BROWSER_SMOKE=1`, a Playwright run of the static frontend in Chromium (`tests/desktop/`).

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

All rights reserved: see [LICENSE](LICENSE). ÆHub is not open source; using, copying, modifying or redistributing it needs the owner's written permission. The third-party components keep their own licenses.

---

# Acknowledgements

ÆHub is built on open-source projects, among them [Python](https://www.python.org/), [FastAPI](https://fastapi.tiangolo.com/), [Pydantic AI](https://ai.pydantic.dev/), [Next.js](https://nextjs.org/), [React](https://react.dev/), [PostgreSQL](https://www.postgresql.org/) and [pgvector](https://github.com/pgvector/pgvector), [Alembic](https://alembic.sqlalchemy.org/), [Redis](https://redis.io/), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/rhasspy/piper), [ONNX Runtime](https://onnxruntime.ai/) with the [sentence-transformers](https://www.sbert.net/) MiniLM model, [Playwright](https://playwright.dev/), [Tauri](https://tauri.app/), [MCP](https://modelcontextprotocol.io/) and [Docker](https://www.docker.com/).

---

**© 2026 Samuele (AeSoul0). All rights reserved.**
