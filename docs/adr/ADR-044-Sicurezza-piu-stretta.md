# ADR-044: Sicurezza più stretta (N5)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N5, richiesto dall'utente)

## Context
- **Eliminazioni:** `delete_path` cancellava per sempre dopo l'approvazione. Un errore, del modello o di chi approva, non si poteva annullare.
- **Approvazioni a voce (ADR-037):** bastava un «sì» qualsiasi, anche per eliminare o sovrascrivere un file.
- **Codice nuovo:** dalle ultime revisioni sono arrivati molti pezzi:
  - V1, F11 e gli ADR-037, 038 e 039;
  - in questa tornata N1–N4, il Codespace e la scorciatoia del Critic.

## Decision
1. **Cestino invece di eliminazione** (`app/files/trash.py`):
   - **Dove finisce:** `delete_path` sposta il file o la cartella in `.aehub-trash/<quando>-<id>/`, in cima alla cartella consentita in cui si trovava. È lo stesso disco, quindi lo spostamento è un rinomina.
   - **Fuori portata:** la cartella è nascosta, quindi nessuno strumento dei file può leggerla, cercarla o svuotarla (`validate_path`).
   - **Cartelle intere:** si possono eliminare anche le cartelle non vuote, perché tornano indietro.
   - **Scadenza:** dopo `AEHUB_TRASH_DAYS` giorni (30) gli elementi spariscono al primo uso successivo.
   - **Pagina STRUMENTI:** sezione Cestino, solo per il proprietario (`/api/tools/trash`). Si può ripristinare un elemento, eliminarlo per sempre o svuotare tutto con un secondo clic.
   - **Ripristino:** torna dov'era, mai sopra un file che c'è adesso. Il percorso salvato passa di nuovo da `validate_path`, quindi un `item.json` modificato non porta fuori dalle cartelle consentite.
2. **«Sì, elimina» per eliminare e sovrascrivere** (`app/instant/approvals.py`):
   - **La domanda:** per `delete_path` e `replace_file` chiede «Per confermare di' "sì, elimina"» (o «sì, sovrascrivi»).
   - **Un «sì» semplice** non decide e ripete la richiesta. Un «no» annulla sempre.
   - **Parole al posto sbagliato:** «elimina» mentre aspetta un altro strumento non decide niente e va al motore.
   - **Pulsanti del Nucleo:** invariati.
   - **Si spegne** con `AEHUB_CONFIRM_DELETIONS=off`.
3. **Revisione di sicurezza** del codice nuovo. Il modello delle minacce è aggiornato con T05–T09 (`docs/security/threat-model.md`). Esito:
   - **Eventi dal vivo (N1, N4):**
     - `answer.final`, `answer.failed` e `reminder.due` vanno solo sul canale dello spazio di lavoro di chi ha dato il comando, come `answer.delta`;
     - l'id del comando è accettato solo con lettere, cifre e trattini (al massimo 64).
   - **Cartelle degli agenti nell'indice (N3):** valgono gli stessi limiti della cartella di lavoro. I link simbolici che escono non sono seguiti, e i file e le cartelle nascosti restano fuori.
   - **`search_in_files` (N4):** ogni file passa da `validate_path` (link simbolici, ÆHub stesso, AppData, file nascosti). Ci sono limiti di dimensione, numero e tempo, e l'output è marcato non affidabile.
   - **Skill `system` (N4):**
     - comandi fissi, sempre liste di argomenti e mai una shell, con l'azione come enum;
     - lo screenshot è salvato solo nella cartella di lavoro, controllato da `validate_path`;
     - promemoria al massimo 20, a 7 giorni, con testi di 200 caratteri.
   - **Scorciatoia del Critic:** limitata ai ruoli semplici senza strumenti che scrivono e senza contenuto esterno. `OutputGuardrail` resta su ogni risposta.
   - **Codespace:**
     - porta privata di GitHub, con host e origini limitati al Codespace;
     - chiavi solo come segreti;
     - Ollama ascolta solo su 127.0.0.1;
     - `https://localhost:<porta>` è accettato come origine per la riscrittura di GitHub (rischio basso: solo una pagina HTTPS sul PC del proprietario, a quella porta, potrebbe averla).
   - **Correzione trovata dalla revisione:** il ripristino dal cestino ora rivalida il percorso (punto 1).
   - **Strumenti usati:** bandit `-ll` sul backend (come in CI) non segnala niente.

## Consequences
- **Un'eliminazione si annulla per 30 giorni.** Lo spazio si libera alla scadenza o svuotando il cestino.
- **A voce eliminare costa due parole in più.** È voluto.
- **Test:**
  - `tests/agent_engine/test_files_skill.py`: cestino, ripristino, mai sopra un file, `item.json` manomesso, scadenza, rimozione;
  - `tests/agent_engine/test_approval_answers.py`: domanda, «sì» semplice respinto, «sì, elimina» che decide, opzione spenta;
  - `frontend/tests/tools.test.tsx`: la sezione Cestino;
  - le quattro route nuove sono nella superficie API e nell'indice delle pagine.
- **Non verificato:** il cestino su un disco diverso da quello del file (una cartella degli agenti su un'unità esterna). `shutil.move` copia ed elimina, quindi è più lento ma corretto.

## Alternatives considered
- **Cestino di sistema** (Windows Cestino, macOS Trash, tramite send2trash): familiare, ma non funziona in Docker e nel Codespace, e porta una dipendenza in più. Scartato per ora.
- **Cestino in `AEHUB_DATA_DIR`:** è fuori dalle cartelle, ma spesso su un altro disco (una copia, non un rinomina) e in Docker non persiste. Scartato.
- **«Sì, elimina» anche sui pulsanti:** il clic è già un'azione esplicita. Non serve.
