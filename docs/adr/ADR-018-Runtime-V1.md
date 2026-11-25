# ADR-018: Runtime V1 — Docker Compose, PostgreSQL e motore agentico nativo

## Status
**Accepted** (2026-10-18)

## Context
La specifica di progetto (Rev. 2.1, §5.3 e §6.7) descrive per V1 un client desktop Tauri v2 con un sidecar Python (`aehub-core`) basato su **LangGraph**, persistenza su **SQLite** (`SqliteSaver`, `aehub.db`) e memoria semantica su **LanceDB/Chroma** embedded.

Il codice ha preso un'altra strada:
- il motore agentico è **nativo** (`app/agent_engine/`: `AgentEngine` → `AgentRuntime` → Worker → `ToolGateway` → `AgentChecker`), con stato persistito in `AgentRun` e approvazioni/idempotenza nel database;
- la persistenza è **PostgreSQL con pgvector**, con code ed eventi su **Redis**;
- il deployment è **Docker Compose** (`docker-compose.yaml`) e il frontend è **Next.js**, servito come web app e non dentro Tauri;
- la CI (`.github/workflows/ci.yml`) esegue i test contro i servizi `pgvector/pgvector:pg15` e `redis:7-alpine`.

Il loop agentico non esegue ancora tool end-to-end (vedi `ROADMAP.md`, M1). Lasciare aperta la scelta dello stack blocca le milestone successive: ognuna (HITL, guardrail, budget, RAG) dipende da dove vivono stato, checkpoint e indici.

## Problem
Specifica e codice divergono su tre punti: framework di orchestrazione (LangGraph o nativo), storage (SQLite/LanceDB o Postgres/pgvector) e packaging (sidecar Tauri o Compose). Senza una decisione esplicita ogni sessione rischia di "avvicinarsi alla specifica" riscrivendo parti che funzionano.

## Options
1. **Allinearsi subito alla specifica** (LangGraph + SQLite + Tauri).
   - *Pro*: coerenza con il documento; installer singolo "zero-setup".
   - *Contro*: riscrittura del runtime, dello stato e dei test esistenti prima ancora che il loop funzioni; LangGraph non fornisce da solo Tool Gateway, HITL legato agli argomenti e budget, che andrebbero comunque scritti.
2. **Tenere lo stack attuale per V1** (motore nativo + Postgres/pgvector + Redis + Compose) e rinviare il packaging desktop.
   - *Pro*: nessuna riscrittura; Postgres offre già BM25 (`tsvector`) e vettori (`pgvector`) per il RAG ibrido del §4.3; lo stesso stack serve da Control Plane in V2 (§6.1).
   - *Contro*: installazione locale più pesante (servono Docker e Compose); l'obiettivo "setup in circa 10 minuti" dipende da uno script `make demo` e non da un installer.
3. **Ibrido immediato**: motore nativo, ma storage SQLite per V1 e Postgres solo per V2.
   - *Pro*: avvio locale più leggero.
   - *Contro*: due backend di persistenza da mantenere e testare, senza vettori/BM25 equivalenti in SQLite.

## Decision
Adottiamo l'**opzione 2**. Per V1, fino al Primo Milestone (§6.8):
- l'orchestrazione resta il **motore nativo** `app/agent_engine`; LangGraph non viene reintrodotto;
- la persistenza resta **PostgreSQL + pgvector**, con Redis per code ed eventi;
- l'ambiente di riferimento è **Docker Compose**, sia in locale sia in CI;
- il client desktop **Tauri v2** viene realizzato dopo il Primo Milestone, come shell sopra frontend e backend già funzionanti. In quel momento si deciderà, con un ADR dedicato, se il sidecar locale userà Postgres embedded o un adattatore SQLite.

## Trade-offs
- **Pro**: le milestone M1–M7 lavorano su un'unica architettura già coperta da test; nessun lavoro viene buttato.
- **Contro**: fino all'arrivo di Tauri V1 non è "zero-setup"; la sicurezza del loopback del §5.3 si traduce per ora in bind su `127.0.0.1`, controllo dell'`Origin` sulla WebSocket e token di sessione hashati (M3).

## Consequences
- La specifica va aggiornata alla **Rev. 2.2**: §5.3 e §6.7 descrivono l'architettura desktop come obiettivo post-milestone, e §4.3 indica pgvector/tsvector come motore RAG di V1.
- Le milestone della `ROADMAP.md` assumono questo stack; un cambio di stack richiede un nuovo ADR che sostituisca questo.
- Il nome "LangGraph" nella UI del Cockpit (§5.1) va inteso come "grafo di esecuzione degli agenti".
