# Installazione: le altre strade e la configurazione

Il README spiega le due strade più semplici (Codespace e Docker Compose). Qui: lo sviluppo locale del backend e del frontend, l'app desktop (sospesa), la configurazione e le note di sicurezza. Ogni variabile è in [configuration.md](configuration.md).

### Option B — Local backend development

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
pip install -r requirements.txt -r requirements-browser.txt -r requirements-dev.txt
```

Start the API:

```bash
uvicorn main:app --host 0.0.0.0 --port 3002
```

### Local frontend development

```bash
cd frontend
npm install
npm run dev
```

The frontend development server runs on:

```text
http://localhost:2003
```

### Option C — Desktop app (Windows)

The desktop app needs no Docker: one installer holds the engine, its own PostgreSQL with pgvector and the frontend (roadmap M14, `docs/adr/ADR-020-Runtime-desktop.md`).

> **Suspended.** Work on the desktop app is paused, and the CI builds no installer: the `desktop-windows` and `desktop-release` jobs run on a version tag only when the repository variable `DESKTOP_RELEASE` is `on`. What follows describes the app as it was last built; it stays the final goal.

- **Install:** run the `AEHub_*-setup.exe` from the GitHub Release of a version tag, or from the `aehub-windows-installer` artifact of the CI (`desktop-windows` job). It installs for the current user, without administrator rights. Without an Authenticode certificate in the CI secrets it is not code-signed, so Windows SmartScreen asks for confirmation.
- **Updates:** on start the app looks for a newer release, signed with the updater's key, and installs it only if you say yes. Releases are published by the CI when `TAURI_SIGNING_PRIVATE_KEY` is among its secrets.
- **First start:** the app creates its database in `%LOCALAPPDATA%\AEHub` and its working folder in `Documents\AEHub`, then opens the Control Plane already logged in. Add a provider key on the setup page: it goes to the Windows Credential Manager, never to a file. Then pick the models, the folders and the voice as with Docker.
- **How it runs:** the window starts `backend/desktop.py`, which runs Postgres and the API on `127.0.0.1` on ports chosen at every start, with live events in-process instead of Redis. The window logs in with a one-time token. Closing the window stops everything.
- **Memory:** the desktop app uses the `hash` embedder, which needs no model download and has weaker recall, until the local embedder is decided (ADR-020).

Building the installer locally needs Rust, Node.js 20, Python 3.12, Visual Studio Build Tools and a PostgreSQL install with pgvector:

```bash
cd frontend && AEHUB_STATIC_EXPORT=1 npm run build && cd ..
python desktop/scripts/bundle.py --pg-root "C:/Program Files/PostgreSQL/17"
python desktop/scripts/smoke_sidecar.py
cd desktop && npm ci && npx tauri build
```

## Configuration

Configuration has three homes:

* **Secrets** (provider API keys, the login key) — the OS keyring, through the launcher (see *First run*) or the desktop app. The backend reads them from its environment.
* **Settings** — model roles, prices, budget and run limits, voice, the tool settings (disabled tools, skill index, MCP servers), memory (on/off, similarity, embedder), the document size limit and the home MQTT broker. Edited in the Control Plane (**Settings**, `GET`/`PUT /api/settings`), stored in the `app_settings` table, applied from the next run without a restart. A setting never edited falls back to the environment variable of the same name, then to its default, so `backend/.env`, CI and tests keep working. Every change is validated as a whole (a Critic equal to a Worker is refused before it is saved) and recorded in the audit log as `settings.update`.
* **Infrastructure** — database, Redis, CORS, paths: environment only (`backend/.env`, root `.env` for Compose).

At startup the backend logs one line per configuration problem (`[CONFIG ERROR]`, `[CONFIG WARNING]`, …): Critic equal to a Worker, a provider without its key, models without a price, a run limit above the monthly budget, a missing working folder. The Settings page shows the same list. The API starts anyway, so the page can fix what it can; runs are refused while an error remains.

**Every variable, with its default, is in [`docs/configuration.md`](configuration.md).**

### Backend `.env` (local development)

Example for running the backend outside Docker:

```env
POSTGRES_URL=postgresql://aehub_user:replace_password@localhost:5432/aehub_db
REDIS_URL=redis://localhost:6379/0
```

Outside Docker, put the keys in your shell environment (for example `AEHUB_SECRET_KEY`, `OPENAI_API_KEY`) rather than in this file. Voice needs no key: it runs on this machine (see Voice).

### Frontend `.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:3002
```

Do not expose private backend secrets through `NEXT_PUBLIC_*` variables.

### Security notes

The backend refuses to start without `AEHUB_SECRET_KEY` (or with the old placeholder value). The launcher creates a random one in the keyring.

The PostgreSQL password is the one secret kept in a file (the root `.env`, ignored by Git), because the database container reads it too. All ports are bound to `127.0.0.1`.

The API answers only to loopback host names (DNS rebinding) and refuses state-changing requests from pages of other origins. For cookies every `localhost` port is the same site, so a page on another local port would otherwise send requests with the owner's session.

**Pages open without login.** Every `/api/` route except `/api/auth/` needs the session cookie. The API's own pages do not: `/docs`, `/redoc` and `/openapi.json` (the description of the routes, no data), the Prometheus `/metrics` (the default counters of the Python process: memory, CPU, garbage collector) and the `/health` probe. This is deliberate for a single-user app on loopback: they answer only on `127.0.0.1` and loopback host names, and the SISTEMA page links them. If you ever publish the API under another name (`AEHUB_ALLOWED_HOSTS`), put a proxy with authentication in front of them.

In the desktop app the database password is generated on first start and kept in the OS keyring, and Postgres listens only on `127.0.0.1` without a Unix socket.

---
