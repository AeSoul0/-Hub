# ADR-020: Runtime desktop — Tauri v2 con Postgres + pgvector incluso

## Status
**Accepted** (2026-10-24, decisione dell'utente sul database; il resto su proposta di M14)

Sostituisce il punto di ADR-018 lasciato aperto: *"si deciderà, con un ADR dedicato, se il sidecar locale userà Postgres embedded o un adattatore SQLite"*.

## Context
L'uscita di M14 chiede un'installazione su una macchina pulita senza Docker per l'utente finale: installazione → onboarding → prima run approvata. Oggi l'app è fatta di quattro container (FastAPI, Next.js, `pgvector/pgvector:pg15`, `redis:7-alpine`). La mappa di M14 (`ROADMAP.md`) ha trovato quattro legami da sciogliere:

| Legame | Dove |
|---|---|
| Postgres | SQLAlchemy (`app/core/db.py`), il modulo legacy psycopg2 `app/core/database.py` (SQL a mano con `JSONB` e `ON CONFLICT`), il tipo `Vector` di pgvector e la ricerca `tsvector` di `MemoryStore`. |
| Redis | `app/core/event_bus.py` (eventi live per WebSocket e SSE) e `CacheService` (rate limit). |
| Origine del frontend | Il cookie di sessione è `SameSite=Lax`. Un webview Tauri (`http://tauri.localhost`) che chiama `127.0.0.1:<porta>` è un altro sito, quindi le fetch partono senza cookie. |
| Peso | torch + sentence-transformers (embedder di default) e Playwright con Chromium. |

## Decision
1. **Database: Postgres + pgvector portabili dentro l'installer** (decisione dell'utente). C'è un solo backend di persistenza, lo stesso di Docker e della CI, e il modulo legacy e la ricerca `tsvector`/pgvector restano come sono.
   - I binari sono quelli dell'installazione PostgreSQL del runner `windows-latest` (`PGROOT`, build ufficiale EDB), ridotti a `bin`, `lib` e `share`. pgvector viene compilato dal suo tag nello stesso job (`nmake /F Makefile.win`).
   - La major è quella del runner, non quella di compose: i dati del desktop e quelli di Docker non si condividono mai. Una major nuova su un'installazione esistente richiede `pg_upgrade`, quindi l'installer la cambia solo con un passo di migrazione dedicato.
2. **Ciclo di vita del database nel processo Python, non in Rust.** `backend/desktop.py` (il *sidecar*) fa queste cose:
   - sceglie la cartella dati per utente: `%LOCALAPPDATA%\AEHub` su Windows, `~/.local/share/aehub` altrove, oppure `AEHUB_DATA_DIR`;
   - al primo avvio esegue `initdb` con `scram-sha-256` e una password casuale salvata nel keyring del sistema (servizio `aehub`, come il launcher di M12);
   - avvia Postgres con `pg_ctl` solo su `127.0.0.1`, su una porta libera scelta all'avvio;
   - crea l'estensione `vector`;
   - alla chiusura ferma Postgres, e all'avvio recupera un `postmaster.pid` rimasto da un arresto brusco.

   Così il ciclo di vita si testa con pytest, anche in CI con i binari di sistema.
3. **Niente Redis sul desktop.** `AEHUB_EVENT_BUS=memory` (o `REDIS_URL=memory://`) usa un bus e una cache in-process. Sul desktop c'è un solo processo e un solo utente, quindi non serve un broker. Docker resta su Redis.
4. **Stessa origine.** Il backend serve anche il frontend, esportato come statico (`output: "export"`, cartella in `AEHUB_FRONTEND_DIR`). La finestra Tauri apre `http://127.0.0.1:<porta>/desktop/launch?token=…`:
   - il token è monouso, generato a ogni avvio, valido pochi secondi e scambiato con il cookie di sessione admin;
   - il token arriva a Tauri solo sulla pipe stdout del sidecar.

   Non serve aprire CORS e il cookie resta `HttpOnly`.
5. **Sicurezza del loopback, in tutte le modalità.**
   - Controllo dell'`Host` (`localhost`, `127.0.0.1`, `[::1]` più `AEHUB_ALLOWED_HOSTS`) contro il DNS rebinding.
   - Controllo dell'`Origin` sui metodi che scrivono. Per `SameSite` le porte non contano, quindi qualsiasi pagina su `localhost:<altra porta>` è *same-site* e porterebbe il cookie con sé.
6. **Packaging del sidecar: una copia dell'interprete CPython ufficiale** (quello della CI, 3.12), con `site-packages` svuotato e reinstallato da `backend/requirements-desktop.txt`. Niente PyInstaller: le skill si caricano con import dinamici (`load_from_package`), che un eseguibile congelato perderebbe. Il desktop esclude torch: vedi il punto 9. Il sidecar parte con `python -I`, quindi `PYTHONPATH` e i pacchetti utente non contano.
7. **Shell Tauri v2 (`desktop/`).**
   - Avvia il sidecar con la pipe stdin aperta, legge una riga JSON di "pronto" (`{"url": …}`) e apre la finestra.
   - Alla chiusura della finestra chiude stdin: il sidecar ferma uvicorn e Postgres.
   - Se Tauri muore, la pipe si chiude lo stesso.
8. **Distribuzione.**
   - Installer NSIS per utente, senza diritti di amministratore.
   - Aggiornamenti con il plugin updater di Tauri, firmati con la chiave dell'updater e pubblicati come GitHub Release. La coppia di chiavi la genera l'utente (`npx tauri signer generate`): la privata va solo nei secret della CI, la pubblica in `tauri.conf.json`. Finché la chiave non c'è, l'updater non è attivo e l'aggiornamento si fa reinstallando.
   - **Niente firma Authenticode per ora:** costa e senza firma SmartScreen mostra un avviso. Si aggiunge quando l'utente avrà un certificato.
9. **Embedder sul desktop: da confermare con l'utente.** Proposta: ONNX locale (`fastembed`, all-MiniLM-L6-v2, gli stessi 384 valori di oggi) al posto di torch, che da solo pesa più di un gigabyte. Fino alla decisione il desktop usa `AEHUB_EMBEDDER=hash`. I browser di Playwright si scaricano al primo uso della skill browser.

## Trade-offs
- **Pro**
  - Un solo database in tutto il progetto, quindi nessuna seconda implementazione della ricerca ibrida da mantenere.
  - Il motore, i test e le eval non cambiano.
  - Il sidecar è testabile senza Tauri.
- **Contro**
  - L'installer porta con sé Postgres (circa 60–80 MB dopo la riduzione) e un processo in più da gestire.
  - pgvector va compilato per Windows in CI.
  - Un arresto brusco lascia un `postmaster.pid` da ripulire.
  - Il bus in-process vale solo per un processo, e il desktop non andrà mai in scala orizzontale (target personale local-first).

## Consequences
- Nuovi file:
  - `backend/desktop.py` e `backend/app/desktop/`: Postgres gestito, token di avvio, file statici;
  - `backend/requirements-desktop.txt`;
  - `desktop/`: progetto Tauri;
  - un job CI `windows-latest` che costruisce l'installer.
- Il controllo di Host e Origin vale anche per Docker. Chi espone l'API in LAN (`AEHUB_HOST=0.0.0.0`) deve aggiungere il proprio host ad `AEHUB_ALLOWED_HOSTS` e la propria origine ad `AEHUB_ALLOWED_ORIGINS`.
- La vista di una run passa da `/control-plane/runs/<id>` a `/control-plane/runs/view?id=<id>`, perché l'export statico non ha route dinamiche.
- Docker Compose resta l'ambiente di sviluppo e della CI.
