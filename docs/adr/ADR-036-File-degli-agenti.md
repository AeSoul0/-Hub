# ADR-036: I file dell'utente per gli agenti

## Status
**Accepted** (2026-11-26, richiesta dell'utente: "gli agenti devono avere la skill di avere accesso al mio filesystem", nelle cartelle che decide lui)

## Context
- **Nessun tool per i file.** Gli agenti potevano solo:
  - cercare nei documenti indicizzati della cartella di lavoro (`search_documents`);
  - lavorare nella sandbox Docker, che è isolata.
- **Controllo pronto ma inutilizzato:** `validate_path` limitava i percorsi alle cartelle di `AEHUB_ALLOWED_DIRS`, ma nessun tool lo usava.
- **Le cartelle si sceglievano solo all'avvio,** dal launcher.

## Decision
1. **Le cartelle le sceglie l'utente.**
   - Una nuova impostazione, `AEHUB_AGENT_FOLDERS`: una lista JSON di cartelle con il percorso completo, che devono esistere.
   - Si aggiunge alle cartelle di lavoro (`AEHUB_ALLOWED_DIRS`, dal launcher).
   - Si modifica da STRUMENTI → Confini, una riga per cartella, e vale dalla chiamata successiva.
2. **Fuori portata anche dentro una cartella scelta:**
   - il codice di ÆHub: la cartella `backend` e la repository intorno, se c'è;
   - i suoi dati (`AEHUB_DATA_DIR`, i modelli vocali, il flight recorder);
   - il file dei dispositivi di casa;
   - ogni file o cartella nascosti (`.ssh`, `.env`, `.config`…);
   - `AppData`.

   È lì che stanno le credenziali e le regole di ÆHub, che un agente non deve poter riscrivere. Le cartelle di lavoro restano usabili anche quando stanno dentro `backend` (il predefinito `./workspace`).
3. **Skill `files`:**

   | Tool | Rischio | Cosa fa |
   |---|---|---|
   | `list_folder` | LOW | cosa c'è in una cartella |
   | `find_files` | LOW | file per nome o schema (`*.pdf`), in una cartella o in tutte |
   | `read_file` | LOW | un file di testo, i primi 200 KB; un file binario lo dice e non lo legge |
   | `write_file` | MEDIUM | un file nuovo; non sostituisce mai |
   | `make_folder` | LOW | una cartella nuova |
   | `move_path` | MEDIUM | sposta o rinomina; non sostituisce mai |
   | `replace_file` | HIGH | sovrascrive un file esistente, con approvazione |
   | `delete_path` | HIGH | elimina un file o una cartella vuota, con approvazione; mai una cartella consentita |

   - **Doppio controllo:** ogni percorso lo controlla il Tool Gateway prima della chiamata (i tool hanno `filesystem_access`) e lo ricontrolla il tool.
   - **Output non affidabile:** la lettura, l'elenco e la ricerca rendono la run non affidabile, così ogni azione HIGH dopo aspetta l'utente.
   - **Limite per run:** le modifiche contano nel limite `AEHUB_RUN_MAX_FILES_MODIFIED`.
4. **Casa:** il controllo del file dei dispositivi guarda solo le cartelle di lavoro; nelle cartelle scelte quel file è comunque protetto (punto 2).

## Consequences
- **Gli agenti lavorano sui file veri:** in Docker, solo sulle cartelle montate nel container; sul PC (app desktop o backend locale), sul filesystem.
- **Nessuna eliminazione di massa:** solo file singoli o cartelle vuote, ognuno con l'approvazione.
- **Test:**
  - `tests/agent_engine/test_files_skill.py`: cartelle, zone protette, ogni tool, e dal Gateway il rifiuto di un percorso esterno e l'attesa dell'approvazione.
  - `frontend/tests/tools.test.tsx`: l'editor delle cartelle.

## Alternatives considered
- **Il disco intero:** più semplice, ma un'istruzione nascosta in una pagina web potrebbe far leggere o scrivere qualsiasi cosa. Le cartelle scelte limitano il danno, e l'utente può comunque scegliere una cartella grande come la home.
- **Eliminare nel cestino del sistema:** più sicuro per gli errori, ma serve una libreria in più per ogni sistema. Con l'approvazione a ogni eliminazione, per ora basta.
- **Rendere modificabile `AEHUB_ALLOWED_DIRS`:** cambierebbe anche la cartella indicizzata dai documenti e il controllo del file di casa. Una lista a parte tiene le due cose distinte.
