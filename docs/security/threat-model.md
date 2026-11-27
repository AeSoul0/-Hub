<!--
@file docs/security/threat-model.md
@description Threat model of ÆHub: trust boundaries, assets, threats and
the controls that answer them (M1, kept up to date since).
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

### Aggiornamento N5 (2026-11-27, ADR-044)

| ID | Minaccia | Impatto | Mitigazione |
|---|---|---|---|
| **T05** | Un file o una pagina (contenuto esterno) chiede all'agente di eliminare o sovrascrivere file. | Perdita di dati (High) | `delete_path` e `replace_file` sono HIGH e attendono sempre l'approvazione. `delete_path` sposta nel cestino nascosto `.aehub-trash`, fuori dalla portata degli strumenti. A voce o scritto serve «sì, elimina» / «sì, sovrascrivi», non un «sì» qualsiasi (ADR-044). |
| **T06** | Un «sì» detto per altro decide un'approvazione in attesa. | Azione non voluta (Medium) | Per eliminare e sovrascrivere servono parole proprie; la parola che conferma un'eliminazione non decide altri strumenti in attesa (ADR-044). |
| **T07** | Il Critic saltato per le risposte semplici lascia passare un'azione. | Azione non controllata (Medium) | Il salto vale solo per i ruoli triage e fast worker, senza strumenti o solo con `search_documents`, su contesto affidabile; tutto il resto passa dal Critic. `AEHUB_CRITIC_SIMPLE=check` lo rimette ovunque. |
| **T08** | Comandi del computer (volume, blocco, screenshot) usati per eseguire altro. | Esecuzione arbitraria (Critical) | Comandi fissi per sistema, liste di argomenti, mai una shell; l'azione è un enum; nessuno strumento del computer in un container (ADR-043). |
| **T09** | Indirizzi e chiavi del Codespace: un altro sito che chiama l'API. | Accesso non autorizzato (High) | Porta privata di GitHub (solo il proprietario), `AEHUB_ALLOWED_HOSTS` e `AEHUB_ALLOWED_ORIGINS` con il solo host del Codespace, `https://localhost:<porta>` aggiunto per la riscrittura di GitHub; chiavi come segreti Codespaces (variabili d'ambiente), mai su file. |

### Aggiornamento N6 (2026-11-27, ADR-045)

| ID | Minaccia | Impatto | Mitigazione |
|---|---|---|---|
| **T10** | Un client manda l'id di una conversazione per leggere o continuare quella di un altro. | Divulgazione (Medium) | La sessione è sempre `<principal autenticato>~<id>`: l'id da solo non porta fuori dalle sessioni del chiamante. L'elenco e i turni leggono solo le run del principal e dello spazio di lavoro del chiamante, mai quelle dei subagenti. Un id che non è lettere, cifre e trattini (al massimo 64) torna alla sessione del principal. |

### Aggiornamento N4, Google (2026-11-27, ADR-046)

| ID | Minaccia | Impatto | Mitigazione |
|---|---|---|---|
| **T11** | Una email o un evento scritto da altri chiede all'agente di mandare posta, inoltrare dati o creare eventi. | Divulgazione, azione non voluta (High) | `gmail_search`, `gmail_read` e `calendar_list_events` sono `untrusted_output`: il testo è dato, mai istruzioni, e dopo averlo letto ogni azione HIGH chiede l'approvazione. `gmail_send` è HIGH e aspetta sempre il sì del proprietario, con destinatari controllati (al massimo 10, niente intestazioni nascoste nell'indirizzo). |
| **T12** | Il token dell'account Google rubato dal disco o dal database. | Accesso alla posta (Critical) | Il refresh token non va mai in un file né nel database: nel portachiavi del sistema (app desktop) o in un secret dell'ambiente; altrimenti resta in memoria e la pagina lo mostra una volta sola. Il token di accesso vive in memoria. Scollegare lo revoca presso Google. |
| **T13** | Un sito avvia o completa il collegamento con un account dell'attaccante. | Posta dell'utente verso un altro account (High) | Solo il proprietario avvia il collegamento (POST con controllo dell'origine). Lo stato è casuale, vale 10 minuti e una sola volta; il codice è legato al verificatore PKCE (S256) che resta nel backend. Collegare e scollegare finiscono nel registro di audit. |

## 4. Policy "Fail Closed"
In caso di fallimento del database, mancata decodifica del token, token scaduto, o policy engine non raggiungibile, la `HTTPException(401)` o `403` viene generata di default. Non esiste un "fallback privileged".
