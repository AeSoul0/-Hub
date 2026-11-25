# ADR-023: Run e approvazioni dal Nucleo e dal Control Plane (F2)

## Status
**Accepted** (2026-10-25, seconda milestone della roadmap del frontend, F2)

## Context
Con F1 il Nucleo mostra il motore al lavoro, ma per fermare una run bisognava aprire il Control Plane, e lì le run erano una tabella dei 50 run più recenti, senza filtri e senza vedere come una run si avvicinava ai suoi limiti. Il backend sapeva già fermare una run (`POST /api/runs/{id}/cancel`) o tutte (`/stop-all`, `/resume`, M4). Mancavano tre cose:

- **Totali live.** I limiti per run (costo, tempo attivo, tool falliti, file modificati) sono controllati nel runtime, ma gli eventi live portavano solo il costo della singola chiamata al modello. L'esito di un tool non era un evento.
- **Storico.** Non c'era un elenco delle run filtrabile.
- **Timeline.** Il flight recorder registra ogni evento di una run, ma nessuna API lo leggeva.

## Decision
1. **Gli eventi live portano i totali della run.**
   - `model.called` aggiunge `details.usage`: costo, token, chiamate, tool, tool falliti, file modificati e secondi attivi della run fino a quel momento.
   - Nuovo evento `tool.completed`, con il nome del tool, `details.succeeded` e gli stessi totali. Parte dopo che il runtime ha contato l'esito, anche quando quell'esito fa scattare il limite dei tool falliti.
2. **`GET /api/runs/live`** aggiunge i limiti per run e, per ogni run viva, il compito (anteprima), il run padre e i totali. I totali si leggono per riferimento dalla run in esecuzione, così sono aggiornati anche tra un salvataggio e l'altro.
3. **`GET /api/runs`** è lo storico del workspace, dalla più recente.
   - Filtri: stato (anche più d'uno, separati da virgola), testo nel compito o nell'id, giorni, sub-agenti sì/no.
   - Paginazione con `limit`/`offset`; uno stato sconosciuto risponde 422.
4. **`GET /api/runs/{id}/events`** è la timeline di una run dal flight recorder: i suoi eventi più l'avvio e la fine dei suoi sub-agenti, al massimo gli ultimi 500. Una riga danneggiata del file si salta; una run di un altro workspace non esiste (404).
5. **Nucleo.**
   - **Scheda RUN:** il pannello di destra ha due schede, EVENTI e RUN. RUN mostra le run della sessione con i totali contro i limiti (ambra all'80%, rosso al limite), il pulsante per fermarle e la timeline: ora relativa dall'inizio e costo cumulato.
   - **Stop totale:** nella barra in alto, **FERMA TUTTO** chiede un secondo clic entro 4 s; poi diventa **MOTORE FERMO · RIPRENDI**.
   - **Interruttore del pannello:** si chiama MOTORE, perché il pannello ora contiene anche le run.
6. **Control Plane nello stile del Nucleo.**
   - Fatte in F2: la barra di navigazione, le pagine Run (in corso, budget, storico con filtri, spesa), Vista della run (panoramica con i limiti, timeline) e Approvazioni, con un modulo CSS condiviso. I testi sono in italiano, come nel Nucleo.
   - Restano per dopo: Memoria (F5), Sicurezza, Impostazioni e Setup (F4).

## Consequences
- Le API e gli eventi nuovi sono in sola lettura e non toccano i tool: `tests/security/test_api_surface.py` li elenca tra le route di gestione.
- Il tempo attivo nei contatori scorre nel browser tra un evento e l'altro e si riallinea a ogni evento o lettura di `/api/runs/live`; un'attesa di approvazione non conta, come nel runtime.
- La CI prova il percorso vero nello smoke del browser: il Control Plane apre su APPROVAZIONI e la run completata compare come "completata" nello storico.
