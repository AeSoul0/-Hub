# Inventario del repository

Lo stato del repository dopo R1 (2026-11-25), prima di `v1.0.0`. La
versione M0 di questo file descriveva il prototipo iniziale; è riassunta in
fondo, nella sezione **Storia**.

## 1. Cartelle

### Backend (`backend/`)
Applicazione FastAPI (Python 3.12). `main.py` monta le route, il middleware
di sicurezza e il frontend statico dell'app desktop; `desktop.py` è il
sidecar dell'app desktop (PostgreSQL e API su `127.0.0.1`).

- `app/agent_engine/`: il motore A.U.R.O.R.A.
  - loop, Critic, routing per ruoli e circuit breaker;
  - Context Manager, budget e limiti, deleghe;
  - l'adapter Pydantic AI (`adapters/`), lo stato durevole (`state/`) e le approvazioni (`approval/`);
  - il loop sta in `runtime.py`, le sue parti in `runtime_tools.py`, `runtime_limits.py`, `runtime_resume.py`, `runtime_state.py` e `runtime_subagents.py` (Q1).

  Vedi `AEHUB_ENGINE_V1.md`.
- `app/runtime/`: Tool Gateway, catena di hash dell'audit e la facciata `aurora.py`.
- `app/api/`: le route HTTP, WebSocket e SSE. L'elenco esatto è in `tests/security/test_api_surface.py`.
- `app/core/`: database e migrazioni Alembic, event bus e cache (Redis o in processo), sicurezza (sessioni, policy, middleware), configurazione a runtime, protezione SSRF, telemetria.
- `app/memory/`: memoria a lungo termine (`store.py`, pgvector e ricerca full-text).
- `app/documents/`: indice dei documenti della cartella di lavoro, con le citazioni.
- `app/skills/`: le skill e i loro tool:
  - web, browser, sandbox, file, memoria, documenti e casa;
  - deleghe;
  - skill importate `SKILL.md`;
  - client MCP (ADR-033): i tool dei server consentiti, a rischio alto finché non lo abbassi;
  - interfaccia (ADR-034): Aurora cambia la lingua delle pagine e l'avviso sulla lingua della voce;
  - indice delle skill.
- `app/voice/`: voce locale (faster-whisper, Piper) ed ElevenLabs facoltativo.
- `app/home/`: dispositivi di casa via MQTT.
- `app/system/`: stato del sistema, log, eval, flight recorder e aggiornamenti per la pagina SISTEMA.
- `app/desktop/`: chiavi nel keyring e avvio per l'app desktop.
- `app/evaluation/`: la suite di eval e il gate di rilascio.
- `app/domain/models/`: i modelli SQLAlchemy, la fonte delle revisioni Alembic.
- `app/agents/`, `app/workers/`: l'orchestratore delle richieste (testo, voce, comandi `/`) e la sandbox Docker. Il budget sta in `app/agent_engine/budget.py`.
- `alembic/`: le revisioni dello schema (ADR-031).

### Frontend (`frontend/`)
Next.js 16 con React 19 e TypeScript. L'interfaccia è in inglese o in italiano (ADR-034, `src/lib/i18n.tsx`), con tema spaziale blu profondo e angoli squircle.
- `src/app/`: le pagine. La home è il Nucleo (`/`); il Control Plane sta sotto `/control-plane`.
- `src/components/`: componenti del Nucleo e del Control Plane.
- `src/lib/`: client API, eventi dal vivo, logica delle pagine.
- `tests/`: test Vitest (Testing Library, jsdom).

### Desktop (`desktop/`)
Guscio Tauri dell'app Windows (ADR-020): `src-tauri/` (Rust), `scripts/` (bundle, smoke test, manifest degli aggiornamenti). **Sospeso** fino a nuovo ordine; resta l'obiettivo finale.

### Altro
- `tests/`: i test del backend (pytest). Coprono motore, sicurezza, database, desktop e unità.
- `evals/`: `run_evals.py` e `baseline.json` del gate.
- `scripts/`:
  - `aehub.py`, il launcher con le chiavi nel keyring;
  - `demo.py`;
  - `check_headers.py`, che controlla l'intestazione `@file` / `@description` dei sorgenti.
- `docs/`: ADR, architettura, copertura del frontend, design, sicurezza.

## 2. Dipendenze

### Backend (`backend/requirements.txt`)
- **Runtime**: FastAPI, Uvicorn, Pydantic 2, pydantic-settings.
- **Modelli**: Pydantic AI (`pydantic-ai-slim` con gli extra openai, groq, anthropic, google) e l'SDK `openai` (ADR-032).
- **Persistenza**: SQLAlchemy, Alembic, psycopg (psycopg2 per il PostgreSQL del desktop), pgvector (PostgreSQL 16+ con l'estensione `vector`).
- **Event bus e cache**: Redis (in processo nell'app desktop).
- **Memoria e documenti**: sentence-transformers (CPU), pypdf.
- **Web e strumenti**: duckduckgo-search, Playwright, BeautifulSoup, mcp.
- **Voce**: faster-whisper, Piper.
- **Casa**: paho-mqtt.
- **Osservabilità**: OpenTelemetry, prometheus-client.
- **Qualità** (`backend/requirements-dev.txt`, fuori dall'immagine): Ruff, pytest, pytest-asyncio. In CI anche bandit, pip-audit, Trivy e TruffleHog.

### Frontend (`frontend/package.json`)
- **Core**: Next.js 16, React 19, TypeScript. Il React Compiler è installato ma spento.
- **Stile**: Tailwind CSS 4, font locali da `@fontsource`.
- **Test e lint**: Vitest, Testing Library, jsdom, ESLint, Prettier.

## 3. Salute del codice
In CI, a ogni push e pull request:
- `ruff check` con BLE001: un `except Exception` deve avere un motivo e una riga di log;
- `scripts/check_headers.py`;
- la suite pytest, che comprende la copertura del frontend e il controllo che ogni indirizzo chiamato dal frontend sia una route vera;
- il gate di prompt injection e il gate delle eval;
- ESLint, Vitest e le due build del frontend;
- lo smoke test nel browser;
- la migrazione dall'immagine Docker.

## Storia
La baseline M0 descriveva un prototipo con:
- un loop LangGraph, LangChain e LiteLLM;
- Groq come unico modello;
- Celery e lo scheduler proattivo;
- Edge-TTS e Silero-VAD per la voce.

Ognuno è stato sostituito:
- il motore nativo (M1–M3, ADR-018);
- la superficie V1 senza Celery (M10, ADR-019);
- la voce locale con faster-whisper e Piper (ADR-021);
- Pydantic AI come strato dei modelli (P1, ADR-032).
