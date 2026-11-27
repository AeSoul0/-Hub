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
  - `streaming.py`: la bozza della risposta mentre il modello scrive (N1, ADR-040).

  Vedi `AEHUB_ENGINE_V1.md`.
- `app/runtime/`: Tool Gateway, catena di hash dell'audit, la chiamata a un tool senza modello (`direct_tool.py`) e la facciata `aurora.py`.
- `app/api/`: le route HTTP, WebSocket e SSE. L'elenco esatto è in `tests/security/test_api_surface.py`.
- `app/core/`: database e migrazioni Alembic, event bus e cache (Redis o in processo), sicurezza (sessioni, policy, middleware), configurazione a runtime, protezione SSRF, telemetria.
- `app/memory/`: memoria a lungo termine (`store.py`, pgvector e ricerca full-text).
- `app/documents/`: indice dei documenti della cartella di lavoro, con le citazioni.
- `app/instant/`: i comandi istantanei (ADR-035): riconoscimento senza modello, lista delle app, esecuzione dal Tool Gateway; `approvals.py`, la domanda breve di una run in attesa e il «sì»/«no» che decide (ADR-037).
- `app/skills/`: le skill e i loro tool:
  - web, browser, sandbox, memoria, documenti e casa;
  - file (ADR-036): elencare, cercare, leggere e scrivere i file nelle cartelle scelte dall'utente; sostituire ed eliminare con approvazione;
  - app (ADR-035): aprire le app della lista e le cartelle note, anche dai comandi istantanei;
  - deleghe;
  - skill importate `SKILL.md`;
  - client MCP (ADR-033): i tool dei server consentiti, a rischio alto finché non lo abbassi;
  - interfaccia (ADR-034): Aurora cambia la lingua delle pagine e l'avviso sulla lingua della voce;
  - indice delle skill.
- `app/voice/`: voce locale (faster-whisper, Piper), ElevenLabs e SpaceXAI facoltativi; `wake.py` consegna i modelli della parola di attivazione (N2, ADR-041).
- `app/memory/` e `app/documents/`: memoria a lungo termine e indice dei documenti; ultimi turni della sessione in ogni run, riassunto delle conversazioni lunghe, cartelle degli agenti indicizzate, modello multilingue fissato (N3, ADR-042).
- `app/skills/system_skill.py` e `app/instant/reminders.py`: volume, tasti multimediali, blocco dello schermo, screenshot, timer e promemoria; `files_skill.search_in_files` cerca dentro i file e i PDF (N4, ADR-043).
- `app/skills/plan_skill.py`: i piani in più passi dei compiti lunghi, salvati nello stato della run (`worker_context["plan"]`) e mostrati nel pannello RUN del Nucleo (N7, ADR-047).
- `app/google/` (`oauth.py`, `api.py`), `app/api/google.py` e `app/skills/google_skill.py`: Google Calendar e Gmail dell'account del proprietario, con OAuth e PKCE; scheda STRUMENTI → Google (`components/control-plane/GoogleCard.tsx`) (N4, ADR-046).
- `app/api/conversations.py`: le conversazioni passate del Nucleo, per sessione (`<principal>~<id>`), con ricerca; pannello CRONOLOGIA (`components/nucleo/HistoryPanel.tsx`) (N6, ADR-045).
- `app/files/trash.py`: il cestino di ÆHub per `delete_path`, con ripristino e scadenza; pagina STRUMENTI → Cestino (`components/control-plane/TrashCard.tsx`) (N5, ADR-044).
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
- `src/lib/`: client API, eventi dal vivo, logica delle pagine; `nucleo/wake.ts` e `nucleo/wakeListener.ts` riconoscono la parola di attivazione nella pagina (onnxruntime-web, N2, ADR-041).
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
  - `codespace.sh`, che installa e avvia ÆHub in GitHub Codespaces (`.devcontainer/devcontainer.json`): PostgreSQL con pgvector, il backend e le pagine servite dal backend su una sola porta.
- `docs/`: la guida d'uso (`guida.md`), installazione, uso dall'API, sviluppo, configurazione, ADR, architettura (`architecture/overview.md`, spostata dal README in N10), copertura del frontend, design, sicurezza.

## 2. Dipendenze

### Backend (`backend/requirements.txt`)
- **Runtime**: FastAPI, Uvicorn, Pydantic 2, pydantic-settings.
- **Modelli**: Pydantic AI (`pydantic-ai-slim` con gli extra openai, groq, anthropic, google) e l'SDK `openai` (ADR-032).
- **Persistenza**: SQLAlchemy, Alembic, psycopg (psycopg2 per il PostgreSQL del desktop), pgvector (PostgreSQL 16+ con l'estensione `vector`).
- **Event bus e cache**: Redis (in processo nell'app desktop).
- **Memoria e documenti**: il modello MiniLM di sentence-transformers su ONNX Runtime, senza torch (ADR-039), pypdf.
- **Web e strumenti**: duckduckgo-search, BeautifulSoup, mcp; Playwright in `requirements-browser.txt`, nell'immagine Docker solo con `AEHUB_BROWSER=1` (ADR-039).
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
