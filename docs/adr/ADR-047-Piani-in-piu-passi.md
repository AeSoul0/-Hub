# ADR-047: Piani in più passi per i compiti lunghi (N7)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N7)

## Context
- Una run aveva 10 turni e 20 chiamate di strumenti. Un compito lungo («trova le fatture, riassumile, scrivi il report») finiva i turni a metà, e una run fermata da un'approvazione o da un nuovo tentativo del Critic ripartiva senza sapere a che punto era.
- Il Nucleo mostrava gli eventi della run, non i passi del compito.

## Decision
1. **Il piano vive nello stato della run** (`worker_context["plan"]`). Si salva con la run dopo ogni strumento, quindi c'è ancora dopo un'approvazione, un nuovo tentativo del Critic o un riavvio.
2. **Due strumenti** (skill `plan`, rischio LOW, attraverso il Tool Gateway):
   - `plan_steps`: il modello scrive il piano, da 2 a 12 passi brevi. Se lo riscrive, un passo già fatto resta fatto.
   - `plan_step`: segna un passo «in corso», «fatto», «fallito» o «saltato», con una nota sul risultato.
   - **Solo nella propria run:** fuori da una run rifiutano, e non scrivono mai il piano di un'altra run.
   - **Non sono idempotenti:** una risposta in cache salterebbe la modifica.
3. **Il modello lo rilegge a ogni turno**, come blocco del livello L1 del contesto, con lo stato di ogni passo e «continua dal passo N».
   - Dopo un contenuto non affidabile anche il blocco del piano è marcato non affidabile.
4. **Ogni run vede gli strumenti del piano** (`tool_selection.ALWAYS_TOOLS`), perché il testo del compito non li nomina. Non tolgono posto agli strumenti scelti dal compito e rispettano `AEHUB_DISABLED_TOOLS`.
5. **Limiti:**
   - le chiamate del piano non contano nei limiti di chiamate, per turno e per run: conta solo il lavoro;
   - una run con un piano ha 2 turni in più per passo, fino a 30;
   - costo, tempo attivo, chiamate fallite e budget restano quelli di `RunLimits`.
6. **Nel Nucleo:**
   - ogni modifica è un evento `plan.updated`;
   - il pannello RUN mostra il piano con lo stato di ogni passo («PIANO · 2/5»), la timeline «piano: N di M passi fatti»;
   - `GET /api/runs/live` e `GET /api/runs/{run_id}` danno il piano salvato, così dopo un ricaricamento c'è ancora, e anche la pagina della run lo mostra.

## Consequences
- **Il piano lo scrive il modello:** la descrizione di `plan_steps` gli dice quando serve (più di circa tre chiamate, o più cose da fare). Una domanda semplice non ne ha e non cambia niente: resta veloce e il Critic può saltarla come prima.
- **Un passo non è una run a sé:** se il Critic chiede un nuovo tentativo, il modello vede i passi già fatti e continua da lì, ma i risultati di quei passi sono nelle osservazioni della run, non rifatti.
- **Non verificato con un modello vero:** quanto spesso un modello locale piccolo scrive davvero un piano. I test usano un modello finto.
