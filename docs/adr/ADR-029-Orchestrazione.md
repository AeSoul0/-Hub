# ADR-029: Orchestrazione e sub-agenti (F8)

## Status
**Accepted** (2026-11-04, ottava milestone della roadmap del frontend, F8)

## Context
- **Sub-agenti:** `spawn_subagent` esisteva con i suoi test (M9). Restringeva tool, permessi e budget a quelli del padre e passava al figlio la contaminazione da contenuti non fidati. Però nessun percorso di produzione lo chiamava: il worker non poteva delegare.
- **Albero delle run:** il figlio non salvava il suo padre, quindi l'albero delle run si ricostruiva solo dagli eventi `subagent.*`.
- **Costi:** il costo di un figlio non contava nel budget del padre. Tre figli potevano spendere tre volte quello che restava al padre.
- **Critic:** i suoi verdetti uscivano come `checker.accepted` e `checker.rejected`, senza tentativo e senza istruzione. Una bocciatura definitiva non usciva affatto.
- **Ruolo:** si poteva solo forzare per tutte le run (`AEHUB_FORCE_ROLE`), non per un comando.

## Decision
1. **Un tool di delega, `delegate_task`, come skill nativa** (`app/skills/orchestration_skill.py`), non un percorso speciale del runtime.
   - Passa dal Tool Gateway come ogni altro tool: policy, schema, guardrail, audit. Un tool spento in STRUMENTI resta spento.
   - Chiede il permesso `agent:invoke`: un admin può delegare, un membro no.
   - Il rischio è MEDIUM: delegare spende soldi, ma ogni azione del figlio ha i propri controlli e le proprie approvazioni.
   - Lo vede solo una run che ne ha bisogno: l'indice delle skill lo sceglie dalle parole del compito (delega, sub-agente, in parallelo, …), come ogni altro tool.
2. **Il runtime dà al tool il contesto della run**, come già fa per la memoria: uno `DelegationScope` (`app/agent_engine/delegation.py`) vale per la durata di una sola chiamata. Contiene il padre, il Principal, i totali vivi del padre e il modo di avviare un figlio, che l'AgentEngine mette nel runtime.
3. **Limiti della delega:**
   - **Un solo livello:** un sub-agente non vede `delegate_task`, e il tool rifiuta comunque la chiamata se arriva da un sub-agente.
   - **Quanti:** al massimo `AEHUB_RUN_MAX_SUBAGENTS` figli per run (nuova impostazione senza riavvio, di default 3). Con 0 la delega è spenta e il tool sparisce.
   - **Budget del figlio:** quello chiesto, mai più di quanto resta al padre. Se non lo chiede, metà di quanto resta.
   - **Il costo del figlio si somma al padre** (`usage.cost`, più `subagents` e `subagent_cost`). Il padre si ferma alla chiamata successiva al modello se ha finito il budget. Il registro mensile lo contava già, perché il figlio registra le proprie chiamate.
   - Anche un figlio fallito o fermato costa al padre quello che ha speso.
4. **Ruolo del figlio:** il padre può chiedere `architect`, `research`, `fast_worker` o `triage`; altrimenti decide il triage. Non può chiedere il Critic. Il ruolo resta salvato nel compito, quindi un figlio ripreso dopo un'approvazione torna allo stesso worker. Il Critic è lo stesso indipendente di ogni run.
5. **La risposta del figlio è contenuto non fidato per il padre:** arriva incapsulata come ogni output non fidato. Dopo, le azioni HIGH del padre chiedono un'approvazione. Il figlio può aver letto una pagina o un documento, e il suo testo può portare un'istruzione iniettata.
6. **Un figlio che aspetta un'approvazione resta parcheggiato da solo.** Il padre riceve lo stato `waiting_approval` e prosegue; approvando, si riprende solo il figlio.
   - Alternativa scartata: parcheggiare anche il padre. Servirebbe una ripresa a catena, e il padre aspetterebbe senza sapere quanto.
   - La risposta di un figlio ripreso così non torna al padre: si legge nella sua run.
7. **Albero delle run:** il figlio salva `parent_run_id`, e `run.started` lo porta con sé.
   - La vista di una run elenca i suoi sub-agenti (ruolo, stato, costo, compito).
   - La cronologia mostra ogni figlio sotto il padre.
   - Il Nucleo li ordinava già così (F2), ma finora il padre lo leggeva solo da `subagent.*`.
8. **I verdetti del Critic nella timeline:**
   - `checker.accepted`, `checker.rejected`, il nuovo `checker.failed` e `retry.requested` portano il tentativo e il massimo (`attempt`, `details.max_attempts`);
   - una richiesta di rifare porta l'istruzione di correzione, una bocciatura il motivo, entrambi troncati a 500 caratteri.
9. **Il ruolo di un comando:** `/api/orchestrator/ask` (campo `role`) e il WebSocket (`role` nel messaggio) accettano un ruolo implementatore.
   - Vale per quel comando, prima di `AEHUB_FORCE_ROLE` e del triage.
   - Resta nel compito, quindi una ripresa usa lo stesso ruolo.
   - Un ruolo sconosciuto o il Critic danno 422 (un errore sul WebSocket).
   - Il Nucleo ha la scelta accanto al campo del comando: "auto" lascia decidere il triage.

## Consequences
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dall'84% all'87%.
- Il figlio ha il tempo massimo che il ResourceManager dà al suo compito.
- Il Nucleo aspetta un comando al massimo 45 secondi (`/api/orchestrator/ask`), quindi una delega lunga avviata da lì può essere interrotta. È un limite che c'era già; va rivisto con la pagina Sistema (F9).
- Gli eval non usano la delega: il loro catalogo di tool non la contiene.
