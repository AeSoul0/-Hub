# ADR-035: Comandi istantanei

## Status
**Accepted** (2026-11-26, richiesta dell'utente del 2026-11-25: i comandi banali, come aprire un'app, partono senza LLM, o con passi già definiti, per avere sempre la risposta più veloce possibile)

## Context
- **Ogni comando passa dal motore:**
  - triage;
  - uno o più turni del modello;
  - il Critic;
  - la risposta.
- **Costo:** per "apri Spotify" o "accendi la luce della cucina" sono secondi e una spesa, per un'azione che non ha niente da capire.
- **Aprire un'app del PC:** oggi nessun tool lo fa.
- **Dove gira il backend:** in Docker non vede le app del PC; sull'app desktop o con un backend locale sì.

## Decision
1. **Riconoscimento senza modello** (`app/instant/matcher.py`). Un comando è istantaneo solo se tutta la frase ha una delle forme fisse, in italiano o in inglese:

   | Forma | Esempi |
   |---|---|
   | Aprire un'app | apri, avvia, lancia, fai partire, esegui; open, launch, start, run |
   | Aprire una cartella | apri la cartella … / open the … folder |
   | Una luce | accendi, spegni; turn/switch on/off |
   | Chiudere a chiave | chiudi a chiave, blocca; lock |

   **Come si riconosce l'oggetto:**
   - dopo il verbo si tolgono solo parole di contorno (articoli, "luce della", "the … light", "porta di");
   - quello che resta deve essere esattamente il nome o l'id di qualcosa che l'utente ha dichiarato: un'app della lista, una cartella nota, una luce o una porta di casa;
   - "Aurora", "per favore", "please" intorno al comando non contano.

   **Va al motore come prima:**
   - una frase con più azioni ("apri Spotify e metti la playlist");
   - un nome sconosciuto;
   - un dettaglio in più ("al 50%");
   - lo sblocco di una porta.

   Così un riconoscimento sbagliato non costa niente: nel caso peggiore si fa la strada normale, più lenta.
2. **Esecuzione dal Tool Gateway.**
   - Il tool riconosciuto passa da `app/runtime/direct_tool.py`, la stessa chiamata senza modello della pagina Casa: policy, schema, audit con la catena hash.
   - Un tool che richiede approvazione, o non disponibile in questo ambiente, lascia il comando al motore.
   - La risposta è una frase fissa nella lingua in cui si è parlato ("Apro Spotify.", "Cucina: light on.").
   - Il Nucleo la segna con "istantaneo · N ms".
3. **Ingresso unico:** il controllo sta in `orchestrator.generate_ai_response`, quindi vale per testo, voce e WebSocket. Un errore inatteso del percorso veloce lascia il comando al motore.
4. **Skill `apps`** (`app/skills/apps_skill.py`), usata anche dal motore nei comandi complessi:

   | Tool | Rischio | Cosa fa |
   |---|---|---|
   | `open_app(app)` | MEDIUM | solo un nome della lista `AEHUB_APPS` |
   | `open_folder(folder)` | LOW | Download, Documenti, Scrivania, Immagini, Musica, Video, nella home |

   **Come parte un'app:**
   - il programma parte staccato, con argomenti fissi e senza shell;
   - su Windows con `DETACHED_PROCESS`, quindi senza finestra di terminale;
   - link, `.lnk` e URI (`spotify:`) passano dall'apertura predefinita del sistema.

   **In un container** (`/.dockerenv` o `AEHUB_IN_CONTAINER=1` nell'immagine) la skill non offre tool: le app sono sul PC, fuori portata.
5. **Impostazioni:**
   - `AEHUB_INSTANT_COMMANDS`: `on` (predefinito) o `off`; spento, tutto va al motore.
   - `AEHUB_APPS`: JSON nome → programma (un percorso, un comando, un link, o una lista di programma e argomenti).
     - Si modifica da Impostazioni → App, una riga per app.
     - È validato come ogni impostazione.
     - Al salvataggio e all'avvio la skill rilegge la lista.

## Consequences
- **Velocità:** dalla frase all'azione ci vogliono 6–13 ms nei test (SQLite), contro i secondi di un giro del motore. Con la voce si aggiunge il tempo del riconoscimento e della sintesi.
- **Niente run, niente Critic e niente costo** per un comando istantaneo. Resta l'audit del Gateway, e nel Nucleo la risposta col tempo.
- **Docker:** le luci e le porte funzionano, perché passano da MQTT; le app e le cartelle del PC no, e il motore lo spiega.
- **Pagina Casa:** ora usa la stessa funzione condivisa per chiamare un tool senza modello.
- **Test:**
  - `tests/agent_engine/test_instant_commands.py`:
    - il riconoscimento, in positivo e in negativo;
    - la validazione della lista;
    - un avvio vero e staccato;
    - il percorso completo con audit, senza che il motore parta;
    - spento, tool disattivato, container.
  - `frontend/tests/instant.test.tsx`: la nota nel Nucleo e l'editor delle app.

- **Due bug trovati provando l'app vera (backend con il frontend statico, database nuovo), corretti con il loro test:**
  - **Impostazioni bloccate:** su un'installazione nuova il Critic usa ancora il modello del Worker, e ogni salvataggio veniva rifiutato per il routing: lingua, "Non mostrare più", lista delle app, anche Aurora. Ora il controllo del Critic scatta solo quando la modifica tocca i modelli (`OPENAI_MODEL`, `AEHUB_CHECKER_MODEL`, `AEHUB_MODEL_ROLES`).
  - **Ricaricamento bloccato:** il ricaricamento di una pagina servita dal backend (app desktop) restava su "Controllo la sessione…". La risposta 304 riceveva la CSP stretta dell'API, che il browser copiava sulla pagina in cache bloccandone gli script. Ora una 304 tiene la CSP della pagina.

## Alternatives considered
- **Un piccolo modello locale per capire l'intento:** più tolleranza sulle frasi, ma centinaia di MB di RAM e risposte meno prevedibili. Le forme fisse più la lista dichiarata bastano per questi comandi; se servirà, il modello si aggiunge per i soli casi incerti.
- **Un terminale nascosto con comandi liberi:** più potente, ma Aurora o una frase sentita per sbaglio potrebbero avviare qualsiasi cosa. La lista scelta dall'utente, senza shell, tiene il rischio a MEDIUM.
- **Una run breve nella pagina Run per ogni comando istantaneo:** costerebbe scritture in più a ogni comando. L'audit basta per sapere cosa è successo.
