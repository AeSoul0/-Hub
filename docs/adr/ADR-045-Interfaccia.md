# ADR-045: Interfaccia (N6)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N6, richiesto dall'utente)

## Context
- **Conversazioni:** il Nucleo mostrava solo la conversazione di questa scheda. Tutti i comandi andavano nella stessa sessione del principal, quindi non si poteva tornare a un discorso di ieri, né ricominciare da zero senza che gli agenti si ricordassero degli ultimi turni.
- **Primo avvio:** cinque passi (chiavi e cartella, modelli, prezzi, budget, controllo). Prezzi e budget hanno già valori predefiniti prudenti, e chi parte per la prima volta non sa ancora quali mettere.
- **Accessibilità:** mai verificata in modo sistematico. Il colore `--faint` (#2c3a5e) era usato per testo (suggerimenti, stati vuoti, segnaposto) con un contrasto di 1,7:1 sul fondo.

## Decision
1. **Conversazioni passate** (`app/api/conversations.py`, `components/nucleo/HistoryPanel.tsx`):
   - **Una conversazione è una sessione.** Il Nucleo crea un id (lettere, cifre e trattini, come l'id di un comando) e lo manda con ogni comando (campo `conversation` di `/ask` e `/listen`). Il motore lavora nella sessione `<principal>~<id>`: gli ultimi turni e il riassunto che gli agenti ricordano (ADR-042) sono quelli di quella conversazione.
   - **Senza id**, o con un id non valido, il comando va nella sessione del principal come prima. Nell'elenco è la conversazione con id `""` (percorso `/api/conversations/_`).
   - **Elenco e ricerca:** `GET /api/conversations?q=` raggruppa le run principali del chiamante (mai quelle dei subagenti, mai di altri principal o spazi di lavoro) per conversazione, dalla più recente. Il titolo è il primo comando; la ricerca legge comandi e risposte e dice in quale comando ha trovato il testo.
   - **Ripresa:** `GET /api/conversations/{id}` dà i turni (comando, risposta, stato, canale), dal più vecchio. Il Nucleo li rimette nella conversazione e il comando successivo continua lì. Una run fermata mostra la riga di sistema («Comando fermato.»), una fallita il suo errore.
   - **Nel Nucleo:** il pannello di sinistra ha due schede, CONVERSAZIONE e CRONOLOGIA. CRONOLOGIA ha la ricerca, l'elenco e «Nuova conversazione». Mentre ci sono comandi in corso la conversazione non cambia, perché le loro risposte appartengono a quella in cui sono partiti.
   - **Nel browser** resta solo l'id della conversazione (`localStorage`, `aehub.nucleo.conversation`), così un ricaricamento continua nella stessa. Il testo resta nel database, come prima.
   - **Non elencati:** i comandi istantanei e le approvazioni a voce non passano dal motore e non lasciano una run.
2. **Primo avvio in tre passi** (`app/control-plane/setup/page.tsx`):
   - **Modello:** lingua, chiave del provider, modello predefinito e Critic; un modello per ruolo resta facoltativo, chiuso.
   - **Cartelle:** la cartella di lavoro e una cartella in più per gli agenti, facoltativa (`AEHUB_AGENT_FOLDERS`; le altre si aggiungono su STRUMENTI). Un percorso non completo è rifiutato prima di salvare.
   - **Voce e controllo:** voce accesa o spenta (`AEHUB_VOICE`), il collegamento alla pagina VOCE, poi il controllo e «Finisci il primo avvio».
   - **Prezzi, budget e catene dei ruoli** partono dai valori predefiniti e restano nelle Impostazioni. Il backend non cambia: il primo avvio finisce quando nessun errore blocca le run, come prima.
3. **Accessibilità verificata:**
   - **Test automatico** (`frontend/tests/a11y.test.tsx`, in CI con gli altri test del frontend): axe-core controlla il Nucleo (conversazione e cronologia), ogni passo del primo avvio, il cestino e l'accesso, in italiano e in inglese. Nomi di pulsanti e campi, ruoli e stati ARIA, elenchi e id.
   - **Contrasto:** axe non lo misura senza un motore di layout, quindi lo stesso test calcola il rapporto WCAG dei colori del testo (`--ink`, `--dim`, `--hint`, `--ice`, `--amber`, `--danger`, `--ok`) su ogni fondo della tavolozza: almeno 4,5:1. `--dim` passa a #8696ba; il nuovo `--hint` (#7385aa) prende il posto di `--faint` per il testo, e `--faint` resta per linee e decorazioni. Il test rifiuta `color: var(--faint)`.
   - **Trovato e corretto:** il bordo trascinabile dei pannelli è un `separator` che prende il focus, quindi ora dice la sua altezza (`aria-valuenow`, `aria-valuetext`).
   - **Tastiera e focus:** ogni controllo è un vero pulsante, collegamento o campo; il focus visibile è il contorno azzurro di `globals.css` o il bordo azzurro dei campi. La barra spaziatrice per parlare non scatta dentro un campo, un pulsante o il bordo dei pannelli.

## Consequences
- Le conversazioni vecchie (prima di N6) sono tutte nella conversazione `""`; da qui in avanti ognuna ha la sua.
- Un'altra scheda o un altro computer continua nella conversazione che ha scelto lì: l'id non viaggia tra i browser.
- L'elenco legge le run del principal a ogni richiesta. Per un uso personale bastano; con molte migliaia di run servirà una tabella delle conversazioni.
- Le pagine del Control Plane non coperte dal test (IMPOSTAZIONI, STRUMENTI, VOCE, MEMORIA, RUN, SISTEMA) usano gli stessi componenti; si aggiungono al test quando cambiano.
