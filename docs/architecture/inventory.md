# Repository Inventory

## 1. Overview
Questa è l'inventory del repository `ÆHub` allo stato attuale (Baseline M0), progettata per mappare i componenti esistenti e identificare i gap verso l'architettura 100/100.

## 2. Directory Structure

### Backend (`backend/`)
Il backend è un'applicazione Python FastAPI strutturata secondo i principi della Clean Architecture.
- `app/api/`: Entry point HTTP (es. `academic.py`, `media.py`, `voice.py`). *Da espandere con le rotte di identity e workflow.*
- `app/agents/`: Definizione degli agenti e dei loro prompt.
- `app/core/`: Configurazioni globali, Pydantic settings.
- `app/memory/`: Astrazioni per la memoria (Long-term, Short-term).
- `app/runtime/`: L'effettivo agent runtime, dove attualmente avviene il loop di esecuzione. *Area critica per l'enforcement delle policy.*
- `app/skills/`: Registri delle skill (Tool collection).
- `app/workers/`: Entry point per l'esecuzione in background.
- `app/workflows/`: Astrazioni per workflow deterministici.
- `tests/`: Suite di test (auth, skills, etc.). Attualmente fallisce a causa di path e dipendenze mancanti nell'ambiente virtuale locale.

### Frontend (`frontend/`)
Il frontend è un'applicazione Next.js basata su React.
- `src/app/`: App router di Next.js.
- `src/components/`: Componenti React riutilizzabili (usa `shadcn/ui` e `radix-ui`).
- `src/lib/`: Utility e client API.
- `src/store/`: Gestione dello stato (usa `zustand`).

## 3. Dependencies

### Backend (`requirements.txt`)
- **Runtime**: FastAPI, Uvicorn, Pydantic, Pydantic-Settings.
- **AI & Agent Core**: LiteLLM, Groq, LangChain, LangGraph, mcp.
- **Persistence**: SQLAlchemy, Asyncpg, psycopg-pool (PostgreSQL).
- **Automation / Web**: Playwright, BeautifulSoup4.
- **Audio / Media**: Edge-TTS, Faster-Whisper, Silero-VAD.
- **Distributed Scale (M4/M13)**: Redis, Celery.
- **Observability**: LangSmith, OpenTelemetry.
- **Code Quality**: Ruff, Pytest.

### Frontend (`package.json`)
- **Core**: Next.js 16, React 18, TypeScript.
- **UI & Style**: Tailwind CSS, Shadcn UI, Radix UI, Lucide React, Recharts.
- **State**: Zustand.
- **Linting**: ESLint, Prettier.

## 4. Code Health
- **Ruff**: Il backend passa al 100% i controlli di linting (`ruff check .` = 0 errori). Ottimo punto di partenza.
- **Pytest**: La suite locale su Windows richiede Microsoft Visual C++ Build Tools per compilare la dipendenza `webrtcvad`. In assenza di tali build tools l'installazione fallisce, bloccando l'esecuzione dei test (`ModuleNotFoundError`). Come previsto dalla roadmap LAN-first (Livello 1), si delegherà l'esecuzione dei test e del backend primario su ambiente Docker, che supererà questa limitazione.
- **Frontend ESLint**: Fallisce con 21 problemi (11 errori, 10 warning) relativi principalmente a "set-state-in-effect" e immutabilità nei widget audio/video. Richiede una rapida passata di stabilizzazione.

## 5. Architectural Gaps Identificati (verso M1-M3)
1. **API**: Le rotte correnti sembrano specializzate (es. `academic.py`) ma mancano rotte core di Control Plane (Workspaces, Approvals, Policies).
2. **Runtime Boundaries**: Attualmente `runtime/` e `agents/` sono accoppiati. Manca un `Policy Engine` isolato e un `Tool Gateway` formale per l'autorizzazione.
3. **Identity**: Nessun modulo esplicito `identity/` o `auth/` (a parte un abbozzo nei test). Bisogna passare da `_sessions: Dict[str, Session]` a persistenza su DB.

---
*Aggiornato: M0 - Truth & Baseline*
