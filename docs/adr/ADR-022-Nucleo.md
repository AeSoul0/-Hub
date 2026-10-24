# ADR-022: Il Nucleo, home del frontend sugli eventi live del motore (F1)

## Status
**Accepted** (2026-10-24, direzione visiva decisa dall'utente; prima milestone della roadmap del frontend, F1)

## Context
Finita V1 a livello di codice, il tag `v1.0.0` aspetta un frontend che controlli almeno il 70–80% del motore (decisione dell'utente). La home di prima era fatta di widget di prova: meteo, lettore musicale, un log di testo e un orchestratore. Non mostrava cosa faceva il motore. La mappa del codice ha trovato quanto segue.

- **Eventi del motore.** `EventDispatcher` scrive ogni evento di una run (`run.started`, `model.called`, `tool.proposed`, `tool.approval_required`, `run.completed`…) solo nel flight recorder JSONL. In tempo reale arrivano soltanto `run.state` e gli eventi delle approvazioni.
- **Sub-agenti.** `spawn_agent` non annuncia né l'inizio né la fine di un sub-agente.
- **Microfono.** La home registrava l'audio ma non ne leggeva il livello. La risposta vocale suonava con un `<audio>` senza analisi.

## Decision
1. **Il motore pubblica dal vivo ogni evento delle run.**
   - `EventDispatcher.dispatch`, oltre al flight recorder, manda l'evento come `engine.event` sui canali della sessione e del workspace.
   - L'invio è un task in background con timeout di 0,5 s: non rallenta la run e non la ferma se il bus è irraggiungibile.
   - Fuori da un event loop non si invia niente.
2. **I sub-agenti si annunciano.** `spawn_agent` emette `subagent.spawned` e `subagent.completed`, con il run padre e il ruolo.
3. **La home `/` diventa il Nucleo**, dietro il controllo della sessione (direzione decisa dall'utente; prototipo in `docs/design/hud-prototype.html`).
   - **Sfera:** al centro una sfera a puntini su canvas 2D, ispirata a `Jakubantalik/thinking-orbs` (MIT), una repo tra le stelle dell'utente. Ogni stato la muove in un modo diverso:
     - ascolto: un'onda la percorre al livello del microfono;
     - ragionamento: compaiono tre orbite;
     - tool: un meridiano luminoso la scansiona;
     - approvazione: diventa ambra dentro un anello tratteggiato;
     - voce: si gonfia al livello della risposta;
     - sub-agenti: ognuno è una piccola luna.
   - **Priorità dello stato:** prima ciò che fa l'utente (ascolto, voce), poi le approvazioni in attesa, poi il motore.
   - **Pannelli:** conversazione a sinistra, eventi del motore a destra. Si allungano trascinando il bordo superiore, solo in verticale e fino a 18 px dalla barra in alto, oppure con le frecce; un doppio clic riporta l'altezza standard. Si possono nascondere. A ogni apertura hanno l'altezza standard (richieste dell'utente).
   - **Approvazioni:** la più vecchia in attesa si decide dal Nucleo; le altre restano nella pagina Approvals.
   - **Voce:** il microfono si accende con il pulsante o con la barra spaziatrice e passa da `/api/orchestrator/listen` (ADR-021). La risposta suona tramite un `AnalyserNode`, così la sfera segue la voce vera.
   - **Run riprese:** la risposta di una run ripresa dopo un'approvazione arriva da `run.resumed`.
4. **Tema spaziale e squircle** (decisioni dell'utente).
   - **Tema:** sempre blu scuro, con un cielo di stelle su tre livelli e una nebulosa tenue dietro ogni pagina.
   - **Squircle:** ogni superficie arrotondata ha `corner-shape: squircle`. I cerchi restano rotondi; dove il browser non conosce la proprietà resta il raggio normale.
   - **Font:** Oxanium, IBM Plex Sans e IBM Plex Mono, inclusi da npm, così l'app funziona offline.
5. **Via i widget di prova della home** e le dipendenze che usavano solo loro: Zustand, Recharts, react-rnd, Radix, lucide e i font Nunito e Quicksand.

## Consequences
- La CI prova il percorso sul motore vero: nello smoke del browser sul desktop, il comando parte dal Nucleo, `tool.approval_required` arriva dal vivo e l'approvazione si dà dal Nucleo.
- Gli eventi live contengono i metadati della run: modello, token, costo, nome del tool e rischio, mai gli argomenti. Gli argomenti di una chiamata in attesa arrivano solo da `/api/approvals`, come prima.
- Il Control Plane prende già colori, font e squircle dal tema globale. La sua riscrittura nello stile del Nucleo spetta a F2.
- La risposta di una run ripresa è solo testo: la voce per quel caso arriva con F3, insieme al selettore delle voci e a ElevenLabs.
