# ADR-025: Modelli per ruolo, chiavi e limiti dal Control Plane (F4)

## Status
**Accepted** (2026-10-26, quarta milestone della roadmap del frontend, F4)

## Context
Con M5 il motore ha cinque ruoli: Architect, Research, Critic (il supervisore che controlla ogni risultato), Fast Worker e Triage. Ogni ruolo ha una catena di modelli con failover. Il ruolo di un compito si sceglie per regole, senza chiamare un modello. Fino a F4 però:

- **Catene dei ruoli:** si scrivevano solo come JSON (`AEHUB_MODEL_ROLES`), nella vecchia pagina Impostazioni in inglese.
- **Parametri solo dall'ambiente, con riavvio:**
  - il ruolo forzato;
  - il server locale;
  - la durata delle approvazioni;
  - il circuit breaker;
  - il budget di contesto.
- **Prezzi:** si copiavano a mano dal listino.

L'utente ha chiesto di scegliere l'LLM di ogni ruolo dall'interfaccia, "supervisore" compreso.

## Decision
1. **Editor dei modelli per ruolo.**
   - **Cinque schede, una per ruolo,** con il loro compito in italiano.
   - **Ruolo predefinito:** mostra il modello che userebbe (`OPENAI_MODEL`, oppure il Critic predefinito) e si può personalizzare.
   - **Ruolo personalizzato:** è una catena ordinata di righe *provider · modello*. Il primo modello si prova per primo, gli altri sono riserve; le righe si spostano su e giù e si tolgono.
   - **Salvataggio:** scrive `AEHUB_MODEL_ROLES` con i soli ruoli personalizzati. "Torna al predefinito" toglie il ruolo dal JSON.
2. **Il Critic resta indipendente, anche nell'interfaccia.**
   - L'editor segna in rosso un modello che il Critic condivide con un altro ruolo, e allo stesso modo un ruolo senza modello; in questi casi non salva.
   - Il backend rifiuta comunque lo stesso caso, come da M5 (fail-closed).
   - Accanto a una catena che usa un provider senza chiave compare un avviso.
3. **Catalogo dei modelli: `GET /api/settings/provider-models/{provider}`.** Dà dei suggerimenti; un nome si può sempre scrivere a mano.
   - **OpenRouter:** l'elenco pubblico, solo i modelli che sanno chiamare tool (servono all'agente), con i prezzi convertiti in USD per 1M di token.
   - **OpenAI:** l'elenco dell'account, con la sua chiave, solo i modelli di chat.
   - **Locale:** `<server locale>/models` (Ollama, LM Studio, vLLM).
   - **Cache e chiavi:** le risposte restano in cache 10 minuti; ogni chiave va solo al suo provider e non torna mai indietro.
   - **Uso:** la tabella dei prezzi può riempire i prezzi mancanti con quelli di OpenRouter.
4. **Nuove impostazioni modificabili senza riavvio,** stesso meccanismo di M12:
   - `AEHUB_FORCE_ROLE`: solo i ruoli che eseguono, mai il Critic; vuoto vuol dire "per regole";
   - `AEHUB_LOCAL_BASE_URL`: solo `http(s)://host[:porta]/percorso`;
   - `AEHUB_APPROVAL_TTL_SECONDS`: da 30 secondi a 24 ore, letto alla creazione di ogni approvazione e al suo consenso;
   - `AEHUB_BREAKER_THRESHOLD` e `AEHUB_BREAKER_COOLDOWN_SECONDS`;
   - `AEHUB_CONTEXT_BUDGET` (almeno 2.000 token) e `AEHUB_SNAPSHOT_EVERY` (da 10 a 20).

   Gli intervalli si controllano lato server con i nuovi campi `minimum` e `maximum` delle impostazioni.
5. **Chiave del server locale.** `AEHUB_LOCAL_API_KEY` entra tra le chiavi del portachiavi: l'app desktop la salva come le altre. L'app desktop ora mostra un campo per ogni chiave che il backend conosce.
6. **Impostazioni e Primo avvio nello stile del Nucleo, in italiano.** Le sezioni sono:
   - controllo della configurazione;
   - chiavi;
   - modelli per ruolo;
   - modelli predefiniti e server locale;
   - prezzi;
   - budget e limiti;
   - motore;
   - cartella di lavoro.

   Il JSON dei ruoli e dei prezzi resta modificabile sotto "Avanzate", così nessun controllo si perde. Il Primo avvio propone l'editor dei ruoli come passo facoltativo.

## Consequences
- La nuova API è in sola lettura e non tocca i tool: `tests/security/test_api_surface.py` la elenca.
- Le chiamate del catalogo a OpenRouter e OpenAI partono solo quando si apre la pagina, e mai con le chiavi di un altro provider.
- Un cambio di breaker, contesto o server locale vale dalla run successiva: il salvataggio ricostruisce il motore e azzera i breaker. Una run già in corso tiene quello con cui è partita.
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dal 51% al 62,5%.
