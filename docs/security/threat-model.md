<!--
@file docs/security/threat-model.md
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
-->

# M1 Security Foundation: Threat Model

## 1. Overview & Trust Boundaries
Il sistema ÆHub/A.U.R.O.R.A. opera in un modello **LAN-first**. Tuttavia, i confini di fiducia (Trust Boundaries) sono rigorosamente definiti secondo la policy **Zero Trust (Fail Closed)**:
- **Client (Frontend)**: Non attendibile. Qualsiasi request (inclusi i widget React) deve esibire credenziali valide.
- **LLM / Runtime**: Il Large Language Model è considerato un attore _non deterministico_ e potenzialmente compromesso (Prompt Injection, Confused Deputy). L'LLM **propone** le azioni.
- **Policy Engine (Backend)**: Enclave attendibile. Valida e autorizza _prima_ dell'esecuzione.
- **Database (PostgreSQL)**: Attendibile, isolato a livello di Workspace.

## 2. Threat Actors
1. **Utente LAN non autenticato**: Tenta di accedere alle API per estrarre informazioni sensibili o eseguire task tramite agenti.
2. **Utente autenticato ma non autorizzato**: (es. `Role.GUEST`) tenta di forzare l'esecuzione di tool riservati ad `ADMIN`.
3. **Attore Esterno via Prompt Injection**: Invia un payload malevolo all'agente per esfiltrare dati dal Workspace di un altro utente.

## 3. Identificazione dei Rischi & Mitigazioni (M1/M2)

| ID | Minaccia (Threat) | Impatto | Mitigazione |
|---|---|---|---|
| **T01** | Spoofing dell'identità tramite Session ID contraffatto o mancante. | Accesso non autorizzato (High) | Rimozione array in-memory. Adozione di `SessionLocal` via SQLAlchemy con token crittografici rotanti (`secrets.token_urlsafe(32)`). Check rigoroso `expires_at`. |
| **T02** | Escalation dei privilegi per esecuzione Tools. | Compromissione del sistema locale (Critical) | Validazione forte tramite `PolicyEngine.authorize`. Il `Role` dell'utente è immutabile da parte dell'LLM. Se fallisce l'autorizzazione, `Fail Closed`. |
| **T03** | Cross-Tenant Data Leak (Workspace Contamination). | Esfiltrazione dati sensibili (High) | Le chiavi primarie delle Sessioni legano l'utente a un `workspace_id`. Tutte le query DB filtreranno in base al `workspace_id` associato al token. |
| **T04** | LLM Confused Deputy via Prompt Injection. | Esecuzione arbitraria (Critical) | L'LLM non esegue mai i Tool direttamente. Genera una sintassi dichiarativa; l'executor verifica con il Policy Engine prima di eseguire il side-effect. |

## 4. Policy "Fail Closed"
In caso di fallimento del database, mancata decodifica del token, token scaduto, o policy engine non raggiungibile, la `HTTPException(401)` o `403` viene generata di default. Non esiste un "fallback privileged".
