# ADR-030: Sistema e osservabilità (F9)

## Status
**Accepted** (2026-11-06, nona milestone della roadmap del frontend, F9)

## Context
- **Stato:** database, bus degli eventi e versione dell'app non si vedevano. Lo diceva solo `/health`, che risponde sempre "ok".
- **Parametri di avvio:** database, Redis, host, origini e cartelle si leggono all'avvio, e il Control Plane non li mostrava.
- **Flight recorder:** ogni evento del motore finisce in un file JSONL, ma si leggeva solo run per run.
- **Eval:** giravano solo da riga di comando.
- **Chiave di accesso:** non si poteva cambiare senza toccare il keyring a mano.
- **RAM** (richiesta dell'utente, ROADMAP §5, F9): la voce restava in memoria per sempre, e non c'era modo di vedere quanta RAM usa ÆHub.

## Decision
1. **Una pagina SISTEMA e un'API `/api/system`, solo per l'admin.**
   - **Stato:** versione dell'app, desktop o server, Python e da quanto è attivo.
   - **Database:** un `SELECT 1` con il tempo di risposta.
   - **Bus degli eventi:** in memoria, oppure Redis con un `PING` di 2 secondi.
   - **Errori:** si vede il motivo, senza password.
2. **Parametri di avvio in sola lettura.** L'elenco è fisso: database, Redis, bus, host, origini, cartelle dei dati, di lavoro, dei modelli vocali, l'indice delle skill, il flight recorder, il file dei dispositivi, i programmi di PostgreSQL e il frontend.
   - Ognuno dice se viene dall'ambiente, è il predefinito o non è impostato.
   - Una password dentro un URL diventa `***`, e nessuna chiave è nell'elenco.
   - Si cambiano solo riavviando: per questo non sono impostazioni.
3. **RAM per processo, con psutil (già tra le dipendenze):**
   - il backend, voce compresa, perché i modelli si caricano nel suo processo;
   - il PostgreSQL integrato, letto da `postmaster.pid`; per questo il desktop ora passa `AEHUB_DATA_DIR`;
   - il Chromium del browser, figlio del backend;
   - il WebView2 della finestra, figlio dell'app desktop;
   - il totale e la RAM libera del computer.
4. **La voce si libera da sola.** Nuova impostazione `AEHUB_VOICE_IDLE_MINUTES` (default 15, 0 = mai).
   - Un controllo ogni minuto toglie dalla cache i motori non usati da quel tempo. Whisper e Piper escono dalla memoria e si ricaricano alla prima frase: 1–2 secondi in più, solo quella volta.
   - Una frase in corso tiene il suo motore fino alla fine.
   - Anche `AEHUB_VOICE` diventa un'impostazione senza riavvio: la voce si accende e si spegne da VOCE.
5. **Aggiornamenti del desktop.**
   - L'app passa la sua versione al motore (`AEHUB_APP_VERSION`).
   - Su richiesta la pagina legge `latest.json` dallo stesso indirizzo dell'updater e dice se c'è una versione più nuova.
   - L'installazione resta all'app, che chiede all'avvio e installa solo un pacchetto firmato.
6. **Flight recorder: ricerca ed esportazione.**
   - Si filtra per testo, tipo (esatto o famiglia, per esempio `tool`), run (con i suoi sub-agenti) e intervallo di tempo.
   - La ricerca mostra i 200 eventi più recenti; l'esportazione scarica tutti quelli trovati in JSONL, dal più vecchio.
   - Si legge sempre e solo lo spazio di lavoro di chi chiede. Una riga rovinata si salta.
7. **Eval dall'interfaccia, in un processo figlio.**
   - La suite modifica lo stato globale del processo (sessioni del database, registro delle skill, bus, ambiente), quindi non gira mai dentro l'API: le run vere continuano.
   - Il figlio gira offline (modelli simulati, database in memoria, nessun costo) e senza segreti: chiavi, token, password e URL vengono tolti dal suo ambiente.
   - Un solo eval alla volta.
   - Con `evals/baseline.json` (un checkout dei sorgenti) è il controllo di release; senza (l'app desktop) dà solo il rapporto.
   - La pagina segue la run finché dura.
8. **Rotazione della chiave di accesso.**
   - Una nuova chiave casuale va nel keyring e vale subito per l'accesso.
   - Tutte le altre sessioni vengono chiuse, quella di chi clicca resta.
   - La chiave si vede una volta sola, nella risposta, e l'audit (`access_key.rotate`) non la contiene.
   - Chiede una conferma (senza: 428).
   - Senza keyring (un server avviato dall'ambiente) la rotazione è rifiutata: andrebbe persa al riavvio.
9. **Avvisi ed errori del backend:** gli ultimi 300 messaggi del logging a livello WARNING o superiore, in memoria. Niente su disco, e un riavvio li azzera.

## Consequences
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dall'87% al 100% delle righe. F10 controlla che la tabella non abbia lasciato fuori nessuna funzione del backend; il tag `v1.0.0` arriva dopo la migrazione a Pydantic AI (P1).
- **WebView2 a finestra ridotta a icona** (memoria al livello basso, sfera ferma): rimandato. La ROADMAP lo vuole solo se libera RAM in modo visibile, e va misurato sull'app vera. La pagina ora mostra la RAM della finestra, quindi la misura si può fare.
- La riga Rust che passa la versione non viene compilata in CI finché il build Tauri gira solo sui tag (scelta dell'utente del 2026-11-04).
- Un eval avviato da qui occupa per qualche decina di secondi un secondo processo Python, con 200–300 MB.
