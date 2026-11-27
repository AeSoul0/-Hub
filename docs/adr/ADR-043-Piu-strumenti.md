# ADR-043: Più strumenti (N4)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N4, richiesto dall'utente). Calendario ed email restano fuori finché l'utente non sceglie il servizio.

## Context
- **File:** gli agenti trovavano i file solo per nome, e un PDF letto con `read_file` risultava «binario».
- **Comandi istantanei:** coprivano app, cartelle, luci e serrature. Volume, musica, blocco dello schermo, screenshot, timer e promemoria passavano dal modello: lento su CPU, e senza un modo di suonare all'ora giusta.

## Decision
1. **`search_in_files` (LOW, output non affidabile), nello skill dei file:**
   - **Cosa cerca:** le righe che contengono un testo, oppure tutte le sue parole, nei file di testo e nei PDF delle cartelle consentite (la cartella di lavoro e quelle degli agenti).
   - **Cosa risponde:** `percorso:L12: riga` per il testo, `percorso:p3: riga` per una pagina di PDF.
   - **Limiti:**
     - file fino a 5 MB;
     - 5000 file;
     - 50 risultati, 3 per file;
     - 20 secondi;
     - esclusi i file e le cartelle nascosti, AppData e ÆHub stesso, come per gli altri strumenti dei file.
2. **`read_file` legge i PDF** pagina per pagina con pypdf, entro gli stessi 200 KB.
   - Un PDF fatto solo di immagini lo dice.
   - Un'immagine si dichiara per tipo e dimensione: per farla descrivere si allega al comando nel Nucleo.
3. **Skill `system`** (`app/skills/system_skill.py`):
   - **Strumenti del computer:**
     - `media_control`: volume su e giù, muto, play/pausa, brano successivo e precedente (LOW);
     - `lock_screen` (LOW);
     - `take_screenshot`: un PNG nella cartella di lavoro (MEDIUM).
   - **Solo dove c'è un computer:** quei tre agiscono sul computer dove gira ÆHub, quindi in un container (Docker, Codespace) non sono offerti.
   - **Comandi fissi, mai una shell:**
     - Windows: tasti multimediali e `LockWorkStation` (PowerShell, rundll32), e uno screenshot con System.Drawing;
     - macOS: osascript, pmset, screencapture;
     - Linux: pactl, playerctl, loginctl e il primo strumento di screenshot che trova.
   - **Timer e promemoria** (LOW, funzionano ovunque): `set_timer`, `set_reminder` (tra N minuti o alle HH:MM), `list_reminders`.
     - **Dove restano:** in memoria nel processo, al massimo 20 e al massimo a 7 giorni. Un riavvio li dimentica, e la risposta lo dice.
     - **Quando scadono:** pubblicano `reminder.due` sul canale dello spazio di lavoro. Il Nucleo scrive «⏰ Promemoria: …», suona e, se la pagina non è in primo piano, manda una notifica di sistema.
     - **Ora:** quella del computer dove gira ÆHub. In un Codespace è UTC.
4. **Comandi istantanei** (`app/instant/matcher.py`):
   - **Frasi fisse:** «alza/abbassa il volume», «muto», «pausa», «prossima canzone», «blocca lo schermo», «fai uno screenshot» e le stesse in inglese.
   - **Con un numero:** «timer di 5 minuti», «ricordami tra 10 minuti / fra mezz'ora / alle 18:30 di …» e le forme inglesi, con i numeri in cifre o a parole.
   - **Come rispondono:** chiamano gli strumenti attraverso il Tool Gateway (policy e audit) e rispondono con una frase fissa nella lingua usata. Tutto il resto va al motore come prima.

## Consequences
- **Velocità:** i comandi di tutti i giorni non aspettano il modello (millisecondi invece di minuti su CPU).
- **Test:**
  - `tests/agent_engine/test_system_skill.py`:
    - le frasi istantanee e quelle che restano al motore;
    - i comandi di ogni sistema, sempre liste di argomenti;
    - niente strumenti del computer in un container;
    - un promemoria che suona sullo spazio di lavoro giusto;
    - un timer da capo a fondo attraverso il gateway.
  - `tests/agent_engine/test_files_skill.py`: la ricerca nei file e nei PDF, la lettura di un PDF.
  - `frontend/tests/streaming.test.tsx`: il promemoria nel Nucleo.
- **Non verificato qui:** i comandi veri su Windows e macOS (manca il computer), e gli strumenti di screenshot di Linux in un desktop reale.

## Alternatives considered
- **Promemoria salvati nel database:** sopravvivono a un riavvio, ma servono una tabella e un riavvio dei timer all'avvio. Rimandato, finché non serve davvero.
- **Descrivere le immagini dentro `read_file`:** richiede un modello con la vista e un formato di risultato con immagini. Per ora l'immagine si allega al comando, che arriva già al modello.
- **Calendario ed email:** dipendono dal servizio (Google, Outlook o CalDAV/IMAP locali), che sceglie l'utente.
