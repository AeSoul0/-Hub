# ADR-019: Superficie di V1 — cosa resta e cosa esce dalle aree in freeze

## Status
**Accepted** (2026-10-23, decisione dell'utente su proposta di M10)

## Context
Dal 2026-10-12 voice, vision, academic, audio/media, Celery e workflows erano in *feature freeze*: solo bugfix e sicurezza, finché il motore agentico non fosse solido. Con M0–M9 il motore lo è: ogni capacità passa dal Tool Gateway (policy, approvazioni, provenienza, audit, budget). Le aree in freeze invece erano in gran parte fuori da questo percorso, rotte o mai collegate:

| Area | Stato trovato in M10 |
|---|---|
| Voice | Tre ingressi: `/api/orchestrator/listen` e `/ws/orchestrator` (usati dalla UI, STT su Groq in cloud) e `/api/voice/stream` (faster-whisper locale, **mai usato dal frontend**, token di login nella query string, nessun controllo di `Origin`). |
| Vision — controllo del computer (`vision_skill`) | Screenshot, OCR e clic/tastiera con pyautogui. Il testo letto dallo schermo risultava *trusted*. `import pyautogui` richiede un display: nel container del backend il caricamento delle skill all'avvio rischiava di fallire. |
| Vision — memoria fotografica (`visual_memory_skill`, `vision_indexer`) | CLIP + chromadb + easyocr. L'indicizzazione passava da Celery e cercava la sessione con un id che da M3 è salvato come hash. Unico utente di chromadb, che aveva 4 advisory senza fix. |
| Academic | Scraper del portale Sapienza con Playwright. Celery riceveva `principal.id` al posto della sessione (sempre fallito); il login 2FA apre una finestra visibile, impossibile nel container; fuori dal Gateway. |
| Media | `/api/media/download` (YouTube → mp3 con yt-dlp): endpoint diretto, fuori dall'agente e dal Gateway; non previsto dalla specifica. |
| Celery | Due `celery_app` diversi; utenti: academic e vision (rotti), un `execute_durable_task` finto e un riassunto delle chat via litellm lanciato dopo ogni messaggio anche senza worker attivo. |
| Workflows | `workflows/engine.py` chiamato solo dal suo test; `register_workflows()` vuoto; scheduler avviato senza job; il "morning briefing" avrebbe riusato sempre lo stesso `run_id`. |
| MCP | Allowlist e output sempre *untrusted* (M3), ma la connessione al server è uno stub e nessuna skill lo registra. |

## Decision
- **Voice: resta.** Esce subito `/api/voice/stream` (codice morto con due debolezze di sicurezza). In M15 la voce diventa un solo percorso local-first (STT e TTS locali) che passa dal Gateway come ogni altro input.
- **MCP: resta.** Il client vero si implementa dopo V1, insieme ai moduli §2.1 Life (Notion, Calendar via server MCP).
- **Escono:** vision (controllo del computer e memoria fotografica), academic, media, Celery (con il container `celery-worker` e l'override GPU), workflows e scheduler.
- Dipendenze rimosse: chromadb, easyocr, open_clip_torch, pyautogui, celery, kombu, yt-dlp, litellm, faster-whisper, silero-vad, webrtcvad, opentelemetry-instrumentation-celery; dall'immagine esce ffmpeg. `torch` resta, perché serve a sentence-transformers (embedder della memoria).
- Un test (`tests/security/test_api_surface.py`) fissa l'elenco esatto delle route: una nuova route va rivista e aggiunta di proposito.

## Come possono tornare
- **Controllo del computer** (§2.2): dopo V1, come tool del Gateway con rischio per azione, approvazione per i clic/tastiera e output dello schermo sempre *untrusted*; in un processo con accesso al display, non nel container.
- **Memoria fotografica**: su `memory_chunks`/pgvector invece di chromadb, se serve.
- **Academic**: dopo V1, se l'utente lo vuole, come connettore del modulo Life: tool del Gateway, output *untrusted*, login interattivo fuori dal container.
- **Routine proattive** (briefing, promemoria): con il modulo Life, sul motore agentico, con un Principal vero e un `run_id` nuovo per ogni esecuzione.
- **Code di lavoro**: solo se un carico reale lo richiede. Oggi lo stato durevole delle run è su PostgreSQL e il motore gira nel processo del backend.

## Trade-offs
- **Pro**: meno codice da proteggere (circa 2.000 righe di backend, 4 file del frontend), un container in meno, nessuna eccezione in `pip-audit`, nessun endpoint che agisce fuori dal Gateway.
- **Contro**: sparisce la funzione YouTube → mp3 e quella del portale universitario; chi le usava dovrà aspettare il modulo Life o farne a meno. I dati già salvati nelle tabelle `academic` e `workflows` restano nel database ma non vengono più letti.
- Il tempo di caricamento delle skill non cambia in modo misurabile (≈5 s prima e dopo su Windows): gli import pesanti erano già lazy.
