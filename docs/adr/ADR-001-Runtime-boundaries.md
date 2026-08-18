# ADR-001: Runtime Boundaries

## Status
**Proposed**

## Context
Attualmente, il repository contiene componenti agentici avanzati (in `app/runtime/` e `app/agents/`) che eseguono task e tool. Tuttavia, l'architettura attuale è parzialmente dichiarativa e il modello linguistico (LLM) ha un accesso troppo diretto o implicito all'infrastruttura sottostante. 
Per raggiungere il livello di maturità 100/100, la regola non negoziabile è: *Il modello non deve mai controllare direttamente i confini infrastrutturali.*

Le decisioni di esecuzione, l'allocazione di budget e l'autorizzazione dei permessi devono avvenire all'esterno dell'LLM, in modo deterministico.

## Problem
Se l'Agent Runtime non separa strettamente la pianificazione dall'esecuzione, introduciamo falle di sicurezza critiche (es. Tool Bypass, Privilege Escalation) e violiamo il principio del "Fail Closed". Non possiamo garantire audit affidabili se l'esecuzione e l'intento non sono distinti.

## Options
1. **Mantenere un loop agentico monolitico**: L'LLM decide il tool e il runtime lo esegue immediatamente. 
   - *Pro*: Semplice da implementare, bassa latenza iniziale.
   - *Contro*: Impossibile imporre policy (RBAC, budget), vulnerabile a prompt injection che forza l'esecuzione di tool critici, difficile intercettare un'approvazione umana (HITL).
2. **Separazione rigorosa dei layer (Pipeline Determinista)**:
   - *Plan*: Il Planner genera un grafo di esecuzione / proposta di tool.
   - *Validate*: Il Runtime verifica che la proposta sia ben formata (schema).
   - *Authorize*: Il Policy Engine verifica i privilegi (RBAC, Identity, Budget).
   - *Approve*: Se il tool è ad alto rischio, il sistema si mette in `WAITING_APPROVAL`.
   - *Execute*: L'Executor esegue l'azione confinata.
   - *Audit*: Si registra la transazione.
   - *Evaluate*: Si valuta l'esito.

## Decision
Scegliamo l'**Opzione 2**. Implementeremo una separazione strutturale tra Planner, Executor e Policy Engine. Il modello emetterà solo intenzioni di esecuzione (Proposal), che verranno intercettate e instradate dal Tool Gateway.

## Trade-offs
- **Latenza aggiuntiva**: Il processo di validazione e policy check aggiunge overhead p95.
- **Complessità architetturale**: Richiede di implementare state machine asincrone per la gestione delle esecuzioni interrotte (es. in attesa di approvazione umana).

## Consequences
- Dovremo refattorizzare `app/runtime` per scinderlo in `planner.py`, `executor.py` e introdurre un `policy_engine.py` (M2).
- Il Tool Gateway (M3) diventerà l'unico choke-point per l'accesso ai tool. Nessun tool potrà essere eseguito direttamente chiamando la sua funzione Python all'interno di una skill.
- Richiede la creazione immediata di un modello di dominio per l'Identità (Workspace, User, Role) in modo che il Policy Engine abbia un contesto su cui operare (M1).
