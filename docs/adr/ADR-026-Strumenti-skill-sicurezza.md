# ADR-026: Strumenti, skill SKILL.md, policy e sicurezza dal Control Plane (F5)

## Status
**Accepted** (2026-10-26, quinta milestone della roadmap del frontend, F5)

## Context
Ogni tool passa dal Tool Gateway: policy, guardrail, approvazioni, provenienza, audit e budget. Fino a F5 però dall'interfaccia non si vedeva quasi niente di tutto questo:

- **Catalogo dei tool:** non si vedeva quali tool avesse l'agente, né il rischio di ciascuno.
- **Policy del workspace:** esisteva nel codice (`WorkspacePolicy`), ma valeva sempre "tutti i tool"; non c'era modo di spegnerne uno.
- **Parametri solo dall'ambiente, con riavvio:**
  - indice delle skill (`AEHUB_TOOL_SELECTION`, `AEHUB_TOOL_TOP_K`);
  - server MCP consentiti (`AEHUB_MCP_ALLOWED_SERVERS`).
- **Pagina Sicurezza:** era ancora nel vecchio stile, in inglese, e non diceva da dove arrivava il contenuto letto dai tool.

L'utente ha chiesto anche di usare le skill scaricate da internet nel formato `SKILL.md`, lo standard aperto di Claude Code, Codex e OpenClaw: "basta scaricarle e integrarle, niente di complicato". Nel 2026 però i registri di skill hanno avuto campagne di skill malevole (ClawHavoc su ClawHub), che nascondevano nelle istruzioni dei downloader e dei payload codificati.

## Decision
1. **Spegnere un tool è un'impostazione: `AEHUB_DISABLED_TOOLS`.**
   - Si cambia senza riavvio, con lo stesso meccanismo di M12: viene validata e scritta nell'audit come `settings.update`.
   - Il `PolicyEngine` la applica attraverso `WorkspacePolicy.denied_tools`.
   - Un tool spento non si mostra al modello. Se il modello lo chiede comunque, la chiamata viene rifiutata ("disabled in the Control Plane") e non parte.
   - L'indice delle skill non lo indicizza.
   - Vale per le run nuove e per ogni chiamata successiva, anche dei sub-agenti.
2. **Indice delle skill e server MCP diventano impostazioni.** `AEHUB_TOOL_SELECTION`, `AEHUB_TOOL_TOP_K` (da 1 a 50) e `AEHUB_MCP_ALLOWED_SERVERS` si leggono con `config_value`: prima il database, poi l'ambiente. Gli indirizzi MCP accettano solo `http(s)`, senza credenziali.
3. **Import di skill `SKILL.md`.**
   - **Da dove arriva:** un link https oppure il testo di un file.
     - Una pagina GitHub del file o della cartella diventa il suo indirizzo `raw.githubusercontent.com`.
     - Il download accetta solo https a ogni rimando, passa dai controlli SSRF a ogni salto e ha un limite di 100.000 caratteri.
   - **Si importa solo il testo:** i file allegati alla skill (`scripts/`, `references/`, `assets/`) restano fuori e niente viene eseguito.
   - **Lettura del front matter:** un parser piccolo legge `name` e `description`, con valori tra virgolette e blocchi `>`/`|`, senza dipendere da una libreria YAML. Il nome diventa uno slug di massimo 64 caratteri.
   - **Avvisi:** l'interfaccia segnala, senza bloccare:
     - comandi che scaricano ed eseguono;
     - blocchi codificati lunghi;
     - frasi che chiedono di ignorare le istruzioni;
     - segreti;
     - file allegati;
     - link esterni.
   - **Una skill nuova parte spenta.** Prima di accenderla, la pagina SKILL ne mostra tutto il testo e gli avvisi.
     - Se si reimporta lo stesso testo, la skill resta com'era.
     - Se il testo è cambiato, la skill si spegne di nuovo finché non la si rilegge.
   - **Salvataggio:** ogni skill sta nella tabella `imported_skills` con il suo SHA-256. Import, accensione, spegnimento ed eliminazione vengono scritti nell'audit (`skill.*`) prima di avvenire.
4. **L'agente usa le skill accese con un solo tool: `use_skill(name)`.**
   - **Cosa restituisce:** il testo `SKILL.md` della skill.
   - **Contenuto non affidabile:** l'output è marcato *untrusted*. Dopo averlo letto la run è segnata, e ogni azione a rischio alto chiede approvazione anche se il tool non la chiede da sé. Ogni azione passa comunque dal Tool Gateway. Una skill non aggiunge tool, non esegue file e non dà permessi.
   - **Cosa vede il modello:** solo i nomi delle skill accese, nello schema del tool. Le descrizioni servono solo all'indice delle skill, così un compito che somiglia a una skill fa scegliere il tool.
   - **Quando esiste:** il tool c'è solo mentre almeno una skill è accesa. Il registro delle skill ora sa quale skill dichiara ogni tool e ricarica i tool di una skill quando cambiano (`refresh_skill`). Un tool si esegue solo dall'implementazione della skill che lo ha dichiarato.
5. **API nuove:**
   - **`GET /api/tools`, in sola lettura:**
     - ogni skill con i suoi tool: rischio, approvazione, rete, file, modifica di file, output non affidabile, acceso o spento;
     - stato dell'indice;
     - cartelle consentite ai tool e host dell'API, in sola lettura perché sono parametri di avvio;
     - server MCP;
     - sandbox: Docker presente, immagine, memoria, rete.
   - **`/api/skills`:** elenco, testo di una skill, import, accensione, eliminazione. Le scritture sono riservate all'admin.
   - **Audit e run:**
     - `GET /api/audit` dice per ogni voce se il tool restituisce contenuto non affidabile e filtra per tool;
     - la vista di una run elenca i tool scelti dall'indice.
6. **Interfaccia, in italiano e nello stile del Nucleo:**
   - **STRUMENTI:**
     - catalogo con un interruttore per ogni tool;
     - indice delle skill;
     - confini: cartelle e host in sola lettura, server MCP modificabili;
     - sandbox.
   - **SKILL:** import da link o da file; per ogni skill testo e avvisi, accensione ed eliminazione con conferma.
   - **SICUREZZA:**
     - catena dell'audit;
     - spiegazione della provenienza;
     - registro con filtri per decisione, per tool e "solo contenuto esterno", comprese le modifiche fatte dal Control Plane.

## Consequences
- `tests/security/test_api_surface.py` elenca le nuove route. Nessuna avvia lavoro: una skill si usa solo attraverso il motore e il Gateway.
- Il primo download di una skill da GitHub fa una richiesta verso `raw.githubusercontent.com`, solo quando l'utente preme Importa.
- Il ponte MCP resta quello di prima: la lista dei server consentiti ora si cambia dall'interfaccia, ma un client MCP vero è fuori da F5.
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dal 62,5% al 74%.
