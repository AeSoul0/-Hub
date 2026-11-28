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
- **Your Google Calendar and Gmail.** Connect your own Google account on STRUMENTI: the agents read your events and mail, create events, and send an email only after your yes. The token stays in the keyring or in a secret, never in a file (ADR-046).
- **Long tasks in steps.** For a task with several things to do, the agent first writes a plan and marks each step as it works; the Nucleo shows the plan with the state of every step. The plan is saved with the run: after an approval, a retry or a restart the run goes on from the step it reached (ADR-047).
- **Deleting is undoable.**
  - What the agents delete goes to ÆHub's trash, out of their reach, and can be restored from STRUMENTI for 30 days.
  - By voice, deleting or overwriting needs "sì, elimina" / "sì, sovrascrivi", not a plain yes (ADR-044).
- **Past conversations.** The Nucleo's HISTORY tab lists your conversations, searches their commands and answers, and opens one to go on with it: the agents remember that conversation, not the others; "New conversation" starts from nothing (ADR-045).
- **Approvals that reach you.** A run that waits for you asks one short question ("May I delete old.txt? Yes or no."); a plain "yes" or "no", spoken or typed, decides it and Aurora answers in a word. A system notification and the tab title tell you when a request waits and ÆHub is not in front (ADR-037).
- **Instant commands.** "Open Spotify", "open the downloads folder", "accendi la luce della cucina": simple commands run at once through the Tool Gateway, without the model, in milliseconds. The apps are the ones you list in Settings → Apps; anything else goes to the engine (ADR-035).
- **Accessible.** Every control works with the keyboard and has a name for screen readers, the text colors meet WCAG AA contrast, and an automatic check (axe-core) runs in CI (ADR-045).
- **An interface for everything.** The Nucleo (home) and the Control Plane cover every route and setting of the backend (`docs/frontend-coverage.md`). They are in English by default, or in Italian (Settings → Language, or ask Aurora); the voice keeps the language of the voice you choose, and a notice says when the two differ (ADR-034).

It is not a multi-user service: there is one owner, and every port listens on `127.0.0.1`.

The engine is described in [`docs/architecture/AEHUB_ENGINE_V1.md`](docs/architecture/AEHUB_ENGINE_V1.md), the decisions in [`docs/adr/`](docs/adr/), and the repository in [`docs/architecture/inventory.md`](docs/architecture/inventory.md).

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

Then open http://localhost:3000/control-plane, sign in with the key printed by `python scripts/aehub.py login-key`, and follow the first-run setup, three steps: the model (key, Worker and a different Critic), the folders, the voice with a final check. Prices, budget and the models of each role start from their defaults. Everything can be changed later in **Settings** without a restart.

The launcher (`scripts/aehub.py`, Python standard library only) keeps every secret in the **OS keyring** — Windows Credential Manager, macOS Keychain or the Linux Secret Service — never in a file:

| Command | What it does |
| --- | --- |
| `setup` | Creates the database password (`.env`) and the Control Plane login key; asks for the provider keys (hidden input) and the agent's working folder; moves any key found in `backend/.env` into the keyring and removes it from the file. |
| `up` / `down` | Starts / stops the stack. `up` reads the keys from the keyring and hands them to `docker compose` through its process environment; `docker-compose.yaml` passes them to the backend container. |
| `secrets` | Which keys are set (never their values). |
| `login-key` | Prints the Control Plane login key. |

On Windows the launcher talks to Credential Manager directly. Elsewhere it needs the `keyring` package (`pip install keyring`), which it also prefers on Windows when installed; both read the same entries (service `aehub`).

**On Windows, with a double click:** open `AEHub.cmd` in the repository folder. It starts Docker Desktop if it is not running, runs `setup` on the first start (keys to Credential Manager, working folder) and `up` afterwards, waits until ÆHub answers and opens it in the browser (the first time on the setup page). It also puts an **ÆHub** icon on the desktop, so the next start is one double click there. `AEHub.cmd -Stop` (or `.\start.ps1 -Stop`) stops it; `-NoBrowser` and `-NoShortcut` skip the browser and the icon. Docker Desktop and Python 3 must be installed.

**The browser skill** (reading web pages with Chromium) needs Chromium in the backend image, which by default leaves it out to stay small. To add it, put `AEHUB_BROWSER=1` in the root `.env` and rebuild with `docker compose build backend`; web search works either way (ADR-039).

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

Other ways (local development, the desktop app) and the configuration: [docs/installation.md](docs/installation.md).

---

# Documentation

| Read | For |
| --- | --- |
| [docs/guida.md](docs/guida.md) | **Everyday use**, in Italian: what to say to Aurora, approvals, folders, voice, the history |
| [docs/installation.md](docs/installation.md) | Local development, the desktop app (suspended), configuration and security notes |
| [docs/usage.md](docs/usage.md) | The API for developers: requests, documents, Python client, voice, home, slash commands |
| [docs/architecture/overview.md](docs/architecture/overview.md) | How ÆHub is built: components, repository, memory and RAG, subagents, observability, security |
| [docs/architecture/AEHUB_ENGINE_V1.md](docs/architecture/AEHUB_ENGINE_V1.md) | The A.U.R.O.R.A. engine in detail |
| [docs/development.md](docs/development.md) | Contributing: schema changes, code quality, tests and agent evaluations |
| [docs/configuration.md](docs/configuration.md) | Every setting and environment variable |
| [docs/frontend-coverage.md](docs/frontend-coverage.md) | Where every backend feature is in the interface |
| [docs/adr/](docs/adr/) | The decisions, one record each |
| [docs/security/threat-model.md](docs/security/threat-model.md) | The threat model |

---

# License

All rights reserved: see [LICENSE](LICENSE). ÆHub is not open source; using, copying, modifying or redistributing it needs the owner's written permission. The third-party components keep their own licenses.

---

# Acknowledgements

ÆHub is built on open-source projects, among them [Python](https://www.python.org/), [FastAPI](https://fastapi.tiangolo.com/), [Pydantic AI](https://ai.pydantic.dev/), [Next.js](https://nextjs.org/), [React](https://react.dev/), [PostgreSQL](https://www.postgresql.org/) and [pgvector](https://github.com/pgvector/pgvector), [Alembic](https://alembic.sqlalchemy.org/), [Redis](https://redis.io/), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/rhasspy/piper), [ONNX Runtime](https://onnxruntime.ai/) with the [sentence-transformers](https://www.sbert.net/) MiniLM model, [Playwright](https://playwright.dev/), [Tauri](https://tauri.app/), [MCP](https://modelcontextprotocol.io/) and [Docker](https://www.docker.com/).

---

**© 2026 Samuele (AeSoul0). All rights reserved.**
