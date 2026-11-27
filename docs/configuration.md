# Configuration

Every variable the backend reads, with its default. The README explains
where each kind lives (keyring, Settings, environment); the index of
`docs/frontend-coverage.md` says which page of the interface shows or
changes each one, and `tests/security/test_frontend_coverage.py` fails when
the backend reads a variable that the index does not name.

## Secrets

Kept in the OS keyring by the launcher (`scripts/aehub.py`) or by the desktop
app, never in a file. The backend reads them from its environment.

| Variable | Purpose |
| --- | --- |
| `AEHUB_SECRET_KEY` | Control Plane login key; required, the API exits without it |
| `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Model providers |
| `AEHUB_LOCAL_API_KEY` | Local OpenAI-compatible server, when it asks for a key |
| `ELEVENLABS_API_KEY` | Optional cloud voice (ADR-024) |
| `XAI_API_KEY` | Optional SpaceXAI (xAI) cloud voice (ADR-038) |
| `AEHUB_MQTT_PASSWORD` | Home MQTT broker, when it needs one |
| `AEHUB_MCP_TOKENS` | Bearer tokens of MCP servers that need a login, as `host=token,host=token` (host with its port, if any); each is sent only to its host (ADR-033) |

## Infrastructure

Environment only (`backend/.env`, the root `.env` for Compose).

| Variable | Purpose | Default |
| --- | --- | --- |
| `POSTGRES_URL` | PostgreSQL with pgvector | none (Compose builds it from `POSTGRES_PASSWORD`) |
| `REDIS_URL` | Event bus and cache; `memory://` keeps them in the process | `redis://localhost:6379/0` |
| `NEXT_PUBLIC_API_URL` | Address of the API for the frontend (build time) | `http://127.0.0.1:3002` |

## Engine, tools, memory, voice and home

The model, price and limit variables (`OPENAI_MODEL`, `AEHUB_CHECKER_MODEL`, `AEHUB_MODEL_ROLES`, `AEHUB_MODEL_PRICES`, `AEHUB_DEFAULT_MODEL_PRICE`, `AEHUB_RUN_*`, `AEHUB_MONTHLY_BUDGET`, `AEHUB_BUDGET_WARNING_RATIO`) and the others marked "also in Settings" or with a page are editable without a restart; a value set there wins over the environment.


| Variable | Purpose | Default |
| --- | --- | --- |
| `AEHUB_MODEL_ROLES` | Models per role (spec 4.1) as JSON: `{"architect": ["openrouter:<model>", "openai:<model>"], "critic": ["local:<model>"], ...}`. Roles: `architect`, `research`, `critic`, `fast_worker`, `triage`. The first entry is the primary model, the others are fallbacks. Providers: `openai`, `openrouter`, `local`, `groq`, `anthropic`, `google` (ADR-032). | every role uses `OPENAI_MODEL` on `openai` |
| `AEHUB_CHECKER_MODEL` | Critic model when `AEHUB_MODEL_ROLES` does not set `critic`. The Critic must differ from every Implementer model, otherwise agent runs are refused. | none |
| `AEHUB_CRITIC_SIMPLE` | `skip`: a simple request (triage or fast-worker role) answered with no tool call, or only read-only ones (`search_documents`), on trusted context, is not sent to the Critic (the timeline shows `checker.skipped`). `check`: the Critic checks these too | `skip` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `GROQ_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | Keys of the providers (keyring); a provider shows up in the role editor once it has its key | none |
| `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL` | Another address for the OpenAI or OpenRouter API | the provider's own |
| `AEHUB_LOCAL_BASE_URL` | OpenAI-compatible local server for the `local` provider (Ollama, LM Studio); also in Settings, key `AEHUB_LOCAL_API_KEY` in the keyring | `http://localhost:11434/v1` |
| `AEHUB_LOCAL_TIMEOUT_SECONDS` | How long one answer of the `local` provider may take; a model on a CPU (Ollama in a codespace, set to 600 there) needs minutes | `60` |
| `AEHUB_FORCE_ROLE` | Skip triage and run every task with this role (also in Settings) | none |
| `AEHUB_BREAKER_THRESHOLD` / `AEHUB_BREAKER_COOLDOWN_SECONDS` | Consecutive failures before a provider is skipped, and how long it stays skipped (also in Settings) | `3` / `60` |
| `AEHUB_MODEL_PRICES` | Prices as JSON, USD per 1M tokens: `{"<model>": {"input": 1.0, "output": 4.0}}`. Unpriced models use a deliberately high fallback price and are flagged as estimated. | none |
| `AEHUB_DEFAULT_MODEL_PRICE` | Fallback price `input,output` | `15,60` |
| `AEHUB_RUN_MAX_COST` / `AEHUB_MONTHLY_BUDGET` | Per-run hard stop and monthly cap, in USD (warning at `AEHUB_BUDGET_WARNING_RATIO`). `AEHUB_RUN_MAX_COST=0` removes the per-run cap; the monthly budget still applies | `2` / `30` (`0.8`) |
| `AEHUB_RUN_TIMEOUT_SECONDS` | Limit on a run's active execution time; waiting for an approval does not count. `0` disables it | `900` |
| `AEHUB_ANSWER_TIMEOUT_SECONDS` | How long the Nucleo waits for a command's answer before giving up (900 in a codespace with Ollama) | `45` |
| `AEHUB_RUN_MAX_FAILED_TOOL_CALLS` | Failed tool calls after which a run stops (`LIMIT_EXCEEDED`), e.g. a loop on a failing tool or test. `0` disables it | `10` |
| `AEHUB_RUN_MAX_SUBAGENTS` | Subagents one run may start with `delegate_task`; their cost counts toward the run. `0` turns delegation off (also in Settings) | `3` |
| `AEHUB_RUN_MAX_FILES_MODIFIED` | Distinct files a run may change through tools flagged `modifies_files`; a call on one more file is refused. `0` disables it | `20` |
| `AEHUB_APPROVAL_TTL_SECONDS` | An approval left undecided this long is denied (30 s – 24 h; also in Settings) | `300` |
| `AEHUB_CONTEXT_BUDGET` | Token budget of one model request, split across the Context Manager levels L0–L5 (spec 4.2; also in Settings) | `88000` |
| `AEHUB_SNAPSHOT_EVERY` | Tool calls between State Snapshots; older calls leave the recent window and are summarized (clamped to 10–20) | `15` |
| `AEHUB_MEMORY_ENABLED` | Cross-session long-term memory: recall at run start, indexing of accepted runs (`on`/`off`; also on the MEMORIA page) | `on` |
| `AEHUB_EMBEDDER` / `AEHUB_EMBEDDING_MODEL` | Memory embedder: `sentence-transformers` (a local MiniLM model on ONNX Runtime, no torch, ADR-039; `all-MiniLM-L6-v2` (English) and `paraphrase-multilingual-MiniLM-L12-v2` (50+ languages, int8, better for Italian, ADR-042) are pinned and checked, another model is named with its commit, `owner/name@<commit>`, and must publish an ONNX export) or `hash` (no download, weaker recall); also on the MEMORIA page | `sentence-transformers` / `all-MiniLM-L6-v2` |
| `AEHUB_MEMORY_MIN_SIMILARITY` | Minimum cosine similarity for a vector match in hybrid retrieval; also on the MEMORIA page | `0.25` |
| `AEHUB_ALLOWED_DIRS` | The working folders (`os.pathsep`-separated), set at start; the first one is the folder searched by `search_documents` | `./workspace` |
| `AEHUB_AGENT_FOLDERS` | JSON list of folders the agents' file tools may use besides the working folders, e.g. `["C:\\Users\\me\\Documents"]`; each must exist. ÆHub's own code and data, the home device file, hidden files and folders, and AppData stay out of reach (ADR-036). Set from the STRUMENTI page | none |
| `AEHUB_DOCUMENTS_MAX_FILE_MB` | Files larger than this are listed in the document index with an error and are not searched (0.1–200; also on the DOCUMENTI page) | `5` |
| `AEHUB_MCP_ALLOWED_SERVERS` | Comma-separated MCP server URLs (Streamable HTTP) the client connects to: https, or http only to this computer; also editable on the STRUMENTI page | none (no MCP server) |
| `AEHUB_MCP_TOOL_RISK` | Comma-separated `tool=low\|medium\|high` for MCP tools. A tool not listed is high and asks for approval on every call (ADR-033); set from the STRUMENTI page | none (every MCP tool high) |
| `AEHUB_UI_LANGUAGE` | Language of the pages: `en` or `it`; set on the Settings page or by Aurora (ADR-034). The voice keeps the language of the chosen voice | `en` |
| `AEHUB_VOICE_LANGUAGE_WARNING` | `on` shows a notice when the chosen voice speaks another language than the interface; its "Don't show this again" sets `off`, Settings or Aurora set it back | `on` |
| `AEHUB_INSTANT_COMMANDS` | `on` runs simple commands (open an app or a folder, a light on or off, lock a door) at once, without the model; anything else goes to the engine (ADR-035). Also in Settings | `on` |
| `AEHUB_APPS` | JSON: the name you say -> the program, a path or a list of program and arguments, e.g. `{"spotify": "spotify", "code": ["code", "--new-window"]}`. Only these apps can be opened (`open_app`), and only when ÆHub runs on this computer, not in a container. Set from Settings → Apps | none |
| `AEHUB_DISABLED_TOOLS` | Comma-separated tools the agent can neither see nor call; set by the switches on the STRUMENTI page | none |
| `FRONTEND_URL` / `AEHUB_ALLOWED_ORIGINS` | Browser origins allowed by CORS and the WebSocket; any other origin cannot send POST, PUT, PATCH or DELETE | `http://localhost:3000` |
| `AEHUB_ALLOWED_HOSTS` | Extra host names the API answers to (comma-separated), besides `localhost`, `127.0.0.1` and `[::1]`; needed when the API is served under another name, e.g. on the LAN | none |
| `AEHUB_HOST` | Bind address of `python main.py` | `127.0.0.1` |
| `AEHUB_EVENT_BUS` | `memory` keeps live events and the cache inside the process, without Redis (the desktop app; also `REDIS_URL=memory://`) | Redis |
| `AEHUB_FRONTEND_DIR` | Static frontend export the API serves from its own origin (the desktop app) | none |
| `AEHUB_DATA_DIR` / `AEHUB_PG_BIN` | Desktop app: folder of the database cluster and logs; folder with `initdb` and `pg_ctl` | `%LOCALAPPDATA%\AEHub` / bundled |
| `AEHUB_VOICE` | `local` (faster-whisper + Piper on this machine) or `off`; also on the VOCE page, no restart | `local` |
| `AEHUB_VOICE_IDLE_MINUTES` | Whisper, Piper and the memory's embedding model leave memory after this long without use and load again when needed; `0` keeps them (also on the VOCE page) | `15` |
| `AEHUB_STT_MODEL` / `AEHUB_STT_LANGUAGE` / `AEHUB_TTS_VOICE` | Whisper model, spoken language (`auto` to detect), Piper voice; also editable on the VOCE page | `base` / `it` / `it_IT-paola-medium` |
| `AEHUB_TTS_ENGINE` | `piper` (on this machine), `elevenlabs` (the reply text goes to ElevenLabs, ADR-024) or `spacexai` (it goes to SpaceXAI, 15 $ per million characters, ADR-038); also editable on the VOCE page | `piper` |
| `AEHUB_ELEVENLABS_VOICE` / `AEHUB_ELEVENLABS_MODEL` | ElevenLabs voice ID and model | none / `eleven_flash_v2_5` |
| `AEHUB_SPACEXAI_VOICE` / `AEHUB_SPACEXAI_LANGUAGE` | SpaceXAI voice (`eve` or `altair`) and the language it reads in, always a code (`it`, `en`, `fr`; never `auto`) | `eve` / `it` |
| `AEHUB_WAKE_WORD` / `AEHUB_WAKE_SENSITIVITY` | Wake word the Nucleo listens for, recognized in the page with openWakeWord on onnxruntime-web, no audio leaves the page before it (ADR-041): `off`, `hey_jarvis`, `alexa`, `hey_mycroft` (pinned release models, SHA-256 checked) or `aurora` (your own model in `<AEHUB_VOICE_MODELS_DIR>/wake/aurora.onnx`); sensitivity `low`, `medium` or `high` (threshold 0.7, 0.5, 0.35). Also on the VOCE page | `off` / `medium` |
| `AEHUB_VOICE_MODELS_DIR` | Where the speech models are downloaded on first use | `~/.cache/aehub/voice` |
| `AEHUB_HOME_DEVICES` | JSON file of the home devices, outside the working folder (see Home devices); optional, devices can also be declared on the CASA page | none |
| `AEHUB_MQTT_URL` / `AEHUB_MQTT_USERNAME` | Home MQTT broker (`mqtt://host:1883`, `mqtts://host:8883`) and user; also editable on the CASA page, without a restart | none |
| `AEHUB_TOOL_SELECTION` / `AEHUB_TOOL_TOP_K` | Skill index: show each run only the tools its task names (`AEHUB_TOOL_TOP_K` 1–50); also editable on the STRUMENTI page | `on` / `6` |
| `AEHUB_SKILL_INDEX_PATH` | The skill index's own SQLite file | `~/.cache/aehub/skill_index.sqlite3` |
