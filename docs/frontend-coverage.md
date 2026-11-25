# Copertura dell'interfaccia: quanto del backend si controlla dalla UI

Il tag `v1.0.0` arriva quando questa tabella è al **100%** (fine di F10) e dopo D1 (migrazioni), P1 (Pydantic AI), R1 (controllo generale) e Q1 (`runtime.py`), come dice la ROADMAP §6 (2026-11-24). Ogni milestone la aggiorna.

**Regole:**
- Una riga conta come coperta (✓) quando la funzione si usa o si cambia dall'interfaccia, il Nucleo o il Control Plane.
- Un parametro di avvio (porte, URL del database, cartelle dei dati) conta come coperto quando la pagina Sistema lo mostra in sola lettura.
- ◐ vuol dire parziale e conta mezzo: per esempio si vede ma non si cambia, o si cambia solo scrivendo JSON.
- ⏸ vuol dire **sospesa**: riguarda solo l'app desktop (Tauri), sospesa dal 2026-11-24. Non conta né tra le coperte né tra le mancanti.

**Ultimo aggiornamento:** Q1, `agent_engine/runtime.py` diviso in moduli (2026-11-25): solo spostamento di codice, nessuna route o impostazione cambiata.
**Copertura:** 51 righe su 51, cioè **100%**, più 2 righe sospese (⏸). F10 ha confrontato la tabella con tutte le route e tutte le impostazioni del backend: l'[indice](#indice-ogni-route-e-ogni-impostazione) in fondo dice quale riga copre ciascuna, e un test in CI lo tiene allineato al codice.

## Conversazione e voce

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 1 | Comando scritto (`POST /api/orchestrator/ask`) | Nucleo, campo comando | ✓ | F1 |
| 2 | Comando a voce (`POST /api/orchestrator/listen`) | Nucleo, microfono | ✓ | F1 |
| 3 | Voce e testo via WebSocket (`/ws/orchestrator`) | stesso controllo di 1 e 2, per altri client (i Canali C1 e C2) | ✓ | F1 |
| 4 | Modello e lingua del riconoscimento vocale | Control Plane → VOCE | ✓ | F3 |
| 5 | Motore della voce (Piper o ElevenLabs), voce, modello, chiave | Control Plane → VOCE | ✓ | F3 |
| 6 | Anteprima della voce | Control Plane → VOCE | ✓ | F3 |
| 7 | Risposta a voce di una run chiesta a voce e ripresa dopo un'approvazione | Nucleo | ✓ | F3 |
| 8 | Modelli vocali già scaricati, con il peso | Control Plane → VOCE | ✓ | F3 |
| 9 | Voce accesa o spenta (`AEHUB_VOICE`) e quando si liberano i modelli (`AEHUB_VOICE_IDLE_MINUTES`) | Control Plane → VOCE, Accensione e memoria | ✓ | F9 |

## Motore e run

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 10 | Eventi live del motore | Nucleo, pannello MOTORE → EVENTI | ✓ | F1 |
| 11 | Approvazioni: elenco e decisione | Nucleo; Control Plane → APPROVAZIONI | ✓ | F1, F2 |
| 12 | Run in corso contro i loro limiti; fermare una run | Nucleo → RUN; Control Plane → RUN | ✓ | F2 |
| 13 | Stop di tutte le run e ripresa | Nucleo, FERMA TUTTO; Control Plane → RUN | ✓ | F2 |
| 14 | Storico delle run con filtri | Control Plane → RUN | ✓ | F2 |
| 15 | Vista di una run e timeline | Control Plane → RUN → Dettagli | ✓ | F2 |
| 16 | Spesa e statistiche | Nucleo (chip del budget); Control Plane → RUN | ✓ | F2 |
| 17 | Albero dei sub-agenti e verdetti del Critic | Control Plane → RUN (cronologia ad albero; Dettagli → SUB-AGENTI e timeline); Nucleo → RUN | ✓ | F8 |
| 18 | Ruolo forzato (`AEHUB_FORCE_ROLE`) e ruolo di un comando | IMPOSTAZIONI → Modelli predefiniti; Nucleo, scelta del ruolo accanto al comando | ✓ | F4, F8 |
| 49 | Delega a un sub-agente (`delegate_task`) e sub-agenti per run (`AEHUB_RUN_MAX_SUBAGENTS`) | STRUMENTI (acceso o spento); IMPOSTAZIONI → Limiti; il contatore nella run | ✓ | F8 |

## Modelli, chiavi e limiti

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 19 | Modelli per ruolo con failover (`AEHUB_MODEL_ROLES`), sui provider OpenAI, OpenRouter, server locale e, da P1, Groq, Anthropic e Google Gemini | IMPOSTAZIONI → Modelli per ruolo (editor, con l'elenco dei modelli di ogni provider; i provider nuovi compaiono quando hanno la chiave) | ✓ | F4, P1 |
| 20 | Modello del Critic | IMPOSTAZIONI → Modelli per ruolo e Modelli predefiniti | ✓ | M12, F4 |
| 21 | Prezzi dei modelli | IMPOSTAZIONI → Prezzi, anche dal listino di OpenRouter | ✓ | M12, F4 |
| 22 | Budget mensile, soglia di avviso, limiti per run | IMPOSTAZIONI | ✓ | M12 |
| 23 | Chiavi dei provider nel portachiavi del sistema (anche Groq, Anthropic e Gemini da P1) | Primo avvio e IMPOSTAZIONI → Chiavi (app desktop); launcher `scripts/aehub.py` | ✓ | M14, F4, P1 |
| 24 | Server locale compatibile OpenAI (`AEHUB_LOCAL_BASE_URL`, chiave) | IMPOSTAZIONI → Modelli predefiniti; Chiavi | ✓ | F4 |
| 25 | Circuit breaker dei provider | IMPOSTAZIONI → Motore | ✓ | F4 |
| 26 | Durata delle approvazioni | IMPOSTAZIONI → Budget e limiti | ✓ | F4 |
| 27 | Budget di contesto e snapshot | IMPOSTAZIONI → Motore | ✓ | F4 |

## Strumenti, skill e sicurezza

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 28 | Catalogo di tool e skill, con il rischio di ciascuno | Control Plane → STRUMENTI | ✓ | F5 |
| 29 | Attivare e disattivare i tool (policy del workspace, `AEHUB_DISABLED_TOOLS`) | STRUMENTI, un interruttore per tool | ✓ | F5 |
| 30 | Skill `SKILL.md` scaricate da internet | Control Plane → SKILL: import da link o file, testo e avvisi, accesa o spenta, eliminazione | ✓ | F5 |
| 31 | Server MCP consentiti | STRUMENTI → Confini | ✓ | F5 |
| 32 | Selezione dei tool (indice delle skill) | STRUMENTI → Indice delle skill; i tool scelti nella vista della run | ✓ | F5 |
| 33 | Cartelle consentite ai tool | STRUMENTI → Confini, in sola lettura (parametro di avvio: si sceglie dal launcher) | ✓ | F5 |
| 34 | Registro di audit, con la provenienza | Control Plane → SICUREZZA | ✓ | M11, F5 |

## Memoria e documenti

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 35 | Memoria: elenco, ricerca, aggiunta, modifica, "mi fido", cancellazione | Control Plane → MEMORIA | ✓ | M11, F6 |
| 36 | Memoria accesa o spenta, embedder, soglia di somiglianza; ricalcolo dei vettori | MEMORIA → Come ricorda | ✓ | F6 |
| 37 | Indice dei documenti, sincronizzazione, caricamento, ricerca; citazioni nelle risposte | Control Plane → DOCUMENTI; chip delle citazioni nel Nucleo e nella vista della run | ✓ | F6 |
| 38 | Dimensione massima dei documenti | DOCUMENTI → Cartella di lavoro | ✓ | F6 |

## Casa

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 39 | Dispositivi e rischio di ogni azione (`home.json`) | CASA: dispositivi, stato, comandi attraverso il Tool Gateway; aprire una porta chiede conferma | ✓ | F7 |
| 40 | Broker MQTT | CASA: indirizzo, utente, password nel portachiavi, prova del collegamento | ✓ | F7 |

## Sistema

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 41 | Accesso e uscita | schermata di accesso; Esci | ✓ | M11 |
| 42 | Primo avvio | Control Plane → Primo avvio | ✓ | M12, F4 |
| 43 | Stato di database (con la revisione dello schema), sidecar, bus degli eventi e aggiornamenti | Control Plane → SISTEMA, Stato e Aggiornamenti | ✓ | F9, D1 |
| 44 | Parametri di avvio in sola lettura (database, Redis, bus, host e nomi dell'API, origini, cartelle dei dati e dei modelli, ambiente, tracce, indirizzi di OpenAI e OpenRouter) | Control Plane → SISTEMA, Parametri di avvio | ✓ | F9, F10 |
| 45 | Flight recorder: ricerca ed esportazione | Control Plane → SISTEMA, Flight recorder | ✓ | F9 |
| 46 | Eval dall'interfaccia | Control Plane → SISTEMA, Eval | ✓ | F9 |
| 47 | Rotazione della chiave di accesso | Control Plane → SISTEMA, Chiave di accesso (solo con il keyring) | ✓ | F9 |
| 48 | RAM dei componenti | Control Plane → SISTEMA, Memoria | ✓ | F9 |
| 50 | Avvisi ed errori recenti del backend (`GET /api/system/logs`) | Control Plane → SISTEMA, Avvisi | ✓ | F9 (riga aggiunta in F10) |
| 51 | Pagine dell'API stessa: documentazione (`/docs`, `/redoc`, `/openapi.json`), metriche Prometheus (`/metrics`), controllo di salute (`/health`) | Control Plane → SISTEMA, API: un link per ciascuna | ✓ | F10 |

## Sospese: solo app desktop (Tauri)

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| S1 | Avvio dell'app desktop: token d'avvio (`GET /desktop/launch/{token}`), launcher (`AEHUB_LAUNCHER`), password del PostgreSQL incorporato (`AEHUB_DESKTOP_DB_PASSWORD`) | l'app desktop stessa: nessun controllo da aggiungere | ⏸ | M14 |
| S2 | WebView2 a finestra ridotta (memoria al livello basso, sfera ferma) | da misurare sull'app vera | ⏸ | rimandato da F9 |

## Storia

| Milestone | Righe coperte | Copertura |
|---|---|---|
| F3 (prima versione della tabella) | 24,5 su 48 | 51% |
| F4 | 30 su 48 | 62,5% |
| F5 | 35,5 su 48 | 74% |
| F6 | 38,5 su 48 | 80% |
| F7 | 40,5 su 48 | 84% |
| F8 (una riga nuova: la delega) | 42,5 su 49 | 87% |
| F9 | 49 su 49 | 100% |
| F10 (confronto con route e impostazioni: due righe nuove, due sospese) | 51 su 51 | 100% |
| D1 (la revisione dello schema nella riga 43) | 51 su 51 | 100% |
| P1 (Groq, Anthropic e Gemini nelle righe 19 e 23) | 51 su 51 | 100% |
| R1 (tolta `POST /api/memory/preferences`, doppione di `POST /api/memory`; nuovo controllo: ogni indirizzo chiamato dal frontend è una route vera, `tests/security/test_frontend_api_routes.py`) | 51 su 51 | 100% |
| Q1 (`runtime.py` diviso in moduli, nessuna route o impostazione cambiata) | 51 su 51 | 100% |

## Indice: ogni route e ogni impostazione

F10 (2026-11-24, aggiornato in P1): l'elenco viene dal codice (`tests/security/test_api_surface.py`, `app/core/runtime_config.py`, `app/system/status.py`) e `tests/security/test_frontend_coverage.py` controlla in CI che non manchi nulla. Una route o un'impostazione nuova va aggiunta qui con la sua riga.

### Route

| Route | Riga |
|---|---|
| `GET /api/approvals` | 11 |
| `POST /api/approvals/{approval_id}` | 11 |
| `GET /api/audit` | 34 |
| `POST /api/auth/login` | 41 |
| `POST /api/auth/logout` | 41 |
| `GET /api/auth/verify` | 41 |
| `GET /api/desktop` | 23 |
| `PUT /api/desktop/secrets` | 23 |
| `GET /api/documents` | 37 |
| `GET /api/documents/passage` | 37 |
| `GET /api/documents/search` | 37 |
| `POST /api/documents/sync` | 37 |
| `POST /api/documents/upload` | 37 |
| `GET /api/events` | 10 |
| `GET /api/home` | 39, 40 |
| `POST /api/home/broker/check` | 40 |
| `PUT /api/home/devices` | 39 |
| `POST /api/home/devices/{device_id}/command` | 39 |
| `POST /api/home/devices/{device_id}/state` | 39 |
| `DELETE /api/memory` | 35 |
| `GET /api/memory` | 35 |
| `POST /api/memory` | 35 |
| `POST /api/memory/reembed` | 36 |
| `DELETE /api/memory/{memory_id}` | 35 |
| `PUT /api/memory/{memory_id}` | 35 |
| `POST /api/orchestrator/ask` | 1 |
| `POST /api/orchestrator/listen` | 2 |
| `GET /api/runs` | 14 |
| `GET /api/runs/live` | 12 |
| `POST /api/runs/resume` | 13 |
| `GET /api/runs/stats` | 16 |
| `POST /api/runs/stop-all` | 13 |
| `GET /api/runs/{run_id}` | 15, 17 |
| `POST /api/runs/{run_id}/cancel` | 12 |
| `GET /api/runs/{run_id}/events` | 15 |
| `GET /api/settings` | 18–27, 29, 31–32, 36, 38, 49 (vedi le impostazioni) |
| `PUT /api/settings` | 18–27, 29, 31–32, 36, 38, 49 (vedi le impostazioni) |
| `POST /api/settings/onboarding` | 42 |
| `GET /api/settings/provider-models/{provider}` | 19 |
| `GET /api/skills` | 30 |
| `POST /api/skills/import` | 30 |
| `DELETE /api/skills/{skill_id}` | 30 |
| `GET /api/skills/{skill_id}` | 30 |
| `PUT /api/skills/{skill_id}` | 30 |
| `GET /api/system` | 43, 44, 48 |
| `POST /api/system/access-key/rotate` | 47 |
| `GET /api/system/evals` | 46 |
| `POST /api/system/evals` | 46 |
| `GET /api/system/events` | 45 |
| `GET /api/system/events/export` | 45 |
| `GET /api/system/logs` | 50 |
| `POST /api/system/updates/check` | 43 |
| `GET /api/tools` | 28, 29, 31–33 |
| `GET /api/voice` | 4, 5, 8, 9 |
| `GET /api/voice/elevenlabs/voices` | 5 |
| `POST /api/voice/speak` | 6 |
| `GET /desktop/launch/{token}` | S1 (sospesa) |
| `GET /docs` | 51 |
| `GET /docs/oauth2-redirect` | 51 |
| `GET /health` | 51 |
| `MOUNT /metrics` | 51 |
| `GET /openapi.json` | 51 |
| `GET /redoc` | 51 |
| `WS /ws/orchestrator` | 3 |

### Impostazioni senza riavvio (IMPOSTAZIONI, VOCE, MEMORIA, CASA, STRUMENTI)

| Impostazione | Riga |
|---|---|
| `AEHUB_APPROVAL_TTL_SECONDS` | 26 |
| `AEHUB_BREAKER_COOLDOWN_SECONDS` | 25 |
| `AEHUB_BREAKER_THRESHOLD` | 25 |
| `AEHUB_BUDGET_WARNING_RATIO` | 22 |
| `AEHUB_CHECKER_MODEL` | 20 |
| `AEHUB_CONTEXT_BUDGET` | 27 |
| `AEHUB_DEFAULT_MODEL_PRICE` | 21 |
| `AEHUB_DISABLED_TOOLS` | 29 |
| `AEHUB_DOCUMENTS_MAX_FILE_MB` | 38 |
| `AEHUB_ELEVENLABS_MODEL` | 5 |
| `AEHUB_ELEVENLABS_VOICE` | 5 |
| `AEHUB_EMBEDDER` | 36 |
| `AEHUB_EMBEDDING_MODEL` | 36 |
| `AEHUB_FORCE_ROLE` | 18 |
| `AEHUB_LOCAL_BASE_URL` | 24 |
| `AEHUB_MCP_ALLOWED_SERVERS` | 31 |
| `AEHUB_MEMORY_ENABLED` | 36 |
| `AEHUB_MEMORY_MIN_SIMILARITY` | 36 |
| `AEHUB_MODEL_PRICES` | 21 |
| `AEHUB_MODEL_ROLES` | 19 |
| `AEHUB_MONTHLY_BUDGET` | 22 |
| `AEHUB_MQTT_URL` | 40 |
| `AEHUB_MQTT_USERNAME` | 40 |
| `AEHUB_RUN_MAX_COST` | 22 |
| `AEHUB_RUN_MAX_FAILED_TOOL_CALLS` | 22 |
| `AEHUB_RUN_MAX_FILES_MODIFIED` | 22 |
| `AEHUB_RUN_MAX_SUBAGENTS` | 49 |
| `AEHUB_RUN_TIMEOUT_SECONDS` | 22 |
| `AEHUB_SNAPSHOT_EVERY` | 27 |
| `AEHUB_STT_LANGUAGE` | 4 |
| `AEHUB_STT_MODEL` | 4 |
| `AEHUB_TOOL_SELECTION` | 32 |
| `AEHUB_TOOL_TOP_K` | 32 |
| `AEHUB_TTS_ENGINE` | 5 |
| `AEHUB_TTS_VOICE` | 5 |
| `AEHUB_VOICE` | 9 |
| `AEHUB_VOICE_IDLE_MINUTES` | 9 |
| `OPENAI_MODEL` | 19, 20 |

### Parametri di avvio (SISTEMA, sola lettura)

| Parametro | Riga |
|---|---|
| `POSTGRES_URL` | 44 |
| `REDIS_URL` | 44 |
| `AEHUB_EVENT_BUS` | 44 |
| `AEHUB_HOST` | 44 |
| `AEHUB_ALLOWED_HOSTS` | 33, 44 |
| `FRONTEND_URL` | 44 |
| `AEHUB_ALLOWED_ORIGINS` | 44 |
| `AEHUB_DATA_DIR` | 44 |
| `AEHUB_ALLOWED_DIRS` | 33, 44 |
| `AEHUB_VOICE_MODELS_DIR` | 44 |
| `AEHUB_SKILL_INDEX_PATH` | 44 |
| `AEHUB_FLIGHT_RECORDER_PATH` | 44 |
| `AEHUB_HOME_DEVICES` | 44 |
| `AEHUB_PG_BIN` | 44 |
| `AEHUB_FRONTEND_DIR` | 44 |
| `AEHUB_TELEMETRY_CONSOLE` | 44 |
| `ENVIRONMENT` | 44 |
| `OPENAI_BASE_URL` | 44 |
| `OPENROUTER_BASE_URL` | 44 |

### Segreti e variabili interne

| Variabile | Cos'è | Riga |
|---|---|---|
| `AEHUB_SECRET_KEY` | chiave di accesso: si ruota da SISTEMA (nel keyring) | 41, 47 |
| `OPENAI_API_KEY` | chiave del provider, nel keyring | 23 |
| `OPENROUTER_API_KEY` | chiave del provider, nel keyring | 23 |
| `ELEVENLABS_API_KEY` | chiave della voce cloud, nel keyring | 5 |
| `AEHUB_LOCAL_API_KEY` | chiave del server locale, nel keyring | 24 |
| `AEHUB_MQTT_PASSWORD` | password del broker, nel keyring | 40 |
| `AEHUB_APP_VERSION` | versione passata dall'app desktop, mostrata in STATO | 43 |
| `AEHUB_LAUNCHER` | segnale interno del launcher del desktop | S1 (sospesa) |
| `AEHUB_DESKTOP_DB_PASSWORD` | password del PostgreSQL incorporato, nel keyring, mai mostrata | S1 (sospesa) |
| `GROQ_API_KEY` | chiave del provider groq, nel keyring (P1) | 23 |
| `ANTHROPIC_API_KEY` | chiave del provider anthropic, nel keyring (P1) | 23 |
| `GEMINI_API_KEY` | chiave del provider google (Gemini), nel keyring (P1) | 23 |
