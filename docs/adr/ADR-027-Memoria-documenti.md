# ADR-027: Memoria e documenti dal Control Plane (F6)

## Status
**Accepted** (2026-10-28, sesta milestone della roadmap del frontend, F6)

## Context
La memoria a lungo termine (M6) e l'indice dei documenti (M13) funzionano nel motore, ma dall'interfaccia se ne controllava poco:

- **Ricordi:** la pagina MEMORIA era nel vecchio stile, in inglese. Mostrava i ricordi, aggiungeva solo preferenze e li dimenticava uno alla volta. Non si poteva cercare, modificare un ricordo, né dichiararne uno affidabile.
- **Parametri solo dall'ambiente, con riavvio:**
  - memoria accesa o spenta (`AEHUB_MEMORY_ENABLED`);
  - somiglianza minima;
  - embedder e modello;
  - dimensione massima dei documenti.
- **Documenti:** non avevano una pagina. Le citazioni `[doc: file#righe]` nelle risposte restavano testo, senza modo di vedere il passaggio citato.

## Decision
1. **Cinque nuove impostazioni senza riavvio**, con il meccanismo di M12 (validate e scritte nell'audit come `settings.update`):
   - `AEHUB_MEMORY_ENABLED`: `on`/`off`; i vecchi valori `0`/`1` dell'ambiente valgono ancora;
   - `AEHUB_MEMORY_MIN_SIMILARITY`: da 0 a 1;
   - `AEHUB_EMBEDDER`: `sentence-transformers` o `hash`;
   - `AEHUB_EMBEDDING_MODEL`: un nome di modello, senza percorsi;
   - `AEHUB_DOCUMENTS_MAX_FILE_MB`: da 0,1 a 200.

   Si leggono a ogni uso. Il cambio di embedder ricostruisce l'embedder alla chiamata successiva.
2. **Vettori dopo un cambio di embedder.** Lo store conta i ricordi i cui vettori vengono da un altro embedder: si trovano ancora per parole, ma non più per significato. `POST /api/memory/reembed` li ricalcola tutti con l'embedder attuale, insieme ai pezzi dei documenti dello stesso workspace.
3. **API della memoria**, sempre nel perimetro dell'utente (workspace e principal):
   - **Elenco:** per tipo, per affidabilità, oppure con una ricerca che usa lo stesso recupero ibrido del motore. Insieme all'elenco arrivano conteggi e stato.
   - **Scrittura:** l'utente scrive fatti, preferenze e regole; gli episodi vengono solo dalle run.
   - **Modifica:** testo e tipo. Il testo nuovo viene ricalcolato come vettore e marcato `user-edit`; un duplicato viene rifiutato.
   - **"Mi fido":** rende affidabile un ricordo scritto dopo contenuti esterni, così una preferenza o una regola entra in ogni run. Passa dalle stesse protezioni di una preferenza (input guardrail, niente segreti) e viene scritto nell'audit come `memory.trust` prima di avvenire.
   - **Dimentica i non affidabili:** `DELETE /api/memory?scope=untrusted`. Il parametro è obbligatorio, così una chiamata sbagliata non cancella tutto.
4. **API dei documenti:**
   - **Caricamento** (`POST /api/documents/upload`):
     - è riservato all'admin con accesso ai file;
     - accetta solo un nome di file semplice e visibile, con estensione supportata, entro la dimensione massima;
     - il file finisce in cima alla cartella di lavoro, mai fuori, nemmeno passando da un symlink;
     - un file con lo stesso nome viene sostituito solo se richiesto.

     Nome, dimensione e SHA-256 vengono controllati prima di scrivere l'audit (`document.upload`), poi il file viene scritto e indicizzato subito.
   - **Ricerca e passaggi:** `GET /api/documents/search` e `GET /api/documents/passage` mostrano all'utente i risultati dell'indice e il testo a cui punta una citazione. Quello che restituiscono va solo sullo schermo, mai a un modello: l'agente cerca ancora con il suo tool `search_documents`.
5. **Interfaccia, in italiano e nello stile del Nucleo:**
   - **MEMORIA:**
     - come ricorda: interruttore, somiglianza, embedder e modello, ricalcolo dei vettori;
     - aggiunta di un ricordo;
     - ricerca e filtri;
     - elenco con modifica sul posto, "Mi fido" e "Dimentica" con conferma;
     - "Dimentica i non affidabili".
   - **DOCUMENTI** (nuova):
     - cartella e totali;
     - sincronizzazione;
     - dimensione massima;
     - caricamento;
     - ricerca con i passaggi;
     - tabella dei file, con l'errore di quelli non leggibili.
   - **Citazioni nelle risposte:** nel Nucleo e nell'esito di una run, ogni `[doc: file#righe]` diventa un chip che apre il passaggio citato. Se la citazione non è nell'indice, lo dice.

## Consequences
- `tests/security/test_api_surface.py` elenca le nuove route. Nessuna avvia lavoro né esegue tool.
- Ricalcolare i vettori con un modello locale lo scarica al primo uso (~90 MB per il predefinito) e può durare qualche secondo per migliaia di ricordi.
- La cartella di lavoro resta un parametro di avvio (launcher o `AEHUB_ALLOWED_DIRS`), mostrato in sola lettura.
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dal 74% all'80%.
