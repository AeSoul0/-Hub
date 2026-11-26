# ADR-037: Approvazioni a voce e notifiche del sistema

## Status
**Accepted** (2026-11-26, richiesta dell'utente: una notifica del sistema per ogni approvazione, e poter rispondere a voce, in breve: "se gli dico sì o no dice ricevuto e continua")

## Context
- **La richiesta si vedeva solo nel Nucleo o in APPROVAZIONI.**
  - Con ÆHub ridotto a icona, dietro un'altra finestra o su un'altra pagina, la richiesta passava inosservata.
  - Intanto il tempo scorreva, e alla scadenza la chiamata veniva negata.
- **A voce non si poteva rispondere:** chi aveva chiesto a voce doveva comunque cliccare.
- **La risposta di una run in attesa era il suo stato.** Il motore restituisce `{"status": "WAITING_APPROVAL", ...}`, e l'orchestratore lo mostrava e lo leggeva ad alta voce come testo.

## Decision
1. **Una domanda breve.**
   - Una run che si ferma su un'approvazione risponde con una sola frase nella lingua dell'interfaccia, con il nome del file o dell'oggetto: «Posso eliminare vecchio.txt? Sì o no.» oppure «May I overwrite piano.md? Yes or no.».
   - Per uno strumento senza frase propria la domanda è generica: «Posso usare mcp tool x? Sì o no.».
2. **Una parola decide.**
   - Mentre un'approvazione è in attesa, un comando fatto solo di un sì o di un no decide la più vecchia, cioè la stessa che mostra il Nucleo. Vale a voce e scritto.
     - Per consentire: «sì», «vai pure», «consenti», «ok procedi», «yes», «go ahead».
     - Per negare: «no», «annulla», «lascia stare», «cancel».
     - Sono ammessi «Aurora,» davanti e «per favore» o «grazie» dopo.
   - La decisione passa dallo stesso percorso del bottone (`record_decision` in `app/api/approvals.py`): evento `approval.decided`, ripresa della run, audit.
   - La risposta è di poche parole, scelte a caso tra alcune: «Ricevuto.», «Ok, procedo.», «Va bene, annullo.». Se ce ne sono altre in attesa, si aggiunge «Ne resta un'altra.».
   - Il risultato della run arriva come quando si clicca, e a voce se la run era stata chiesta a voce (F3).
   - Restano al motore, come prima:
     - una frase più lunga («sì, ma prima dimmi cosa c'è»);
     - un sì o un no quando non c'è niente in attesa.
3. **Notifica del sistema** (`ApprovalNotifier`, su ogni pagina).
   - Quando arriva una richiesta e l'utente non la vedrebbe (finestra non in primo piano, scheda nascosta, o una pagina senza il riquadro), una notifica del sistema mostra lo strumento, gli argomenti e la scadenza.
     - Resta finché non la chiudi.
     - Cliccata, porta ÆHub davanti, sul Nucleo.
     - Si chiude da sola quando la richiesta è decisa o scade.
   - Il titolo della scheda conta le richieste in attesa: «(1) ÆHub».
   - Il permesso si chiede una volta, al primo comando inviato dal Nucleo (i browser lo concedono solo dopo un clic), oppure dal bottone in APPROVAZIONI, che mostra anche lo stato: attive, bloccate dal browser, non disponibili.
   - Le notifiche usano lo stesso stream di eventi dell'interfaccia: una sola connessione per pagina.

## Consequences
- **Decidere resta un gesto esplicito.** Una parola vale quanto il bottone, ma solo se è tutta la frase. La decisione riguarda una sola chiamata, con gli argomenti già controllati dal Gateway.
- **Rischio accettato:** chi dice «sì» per un'altra ragione, mentre un'approvazione è in attesa, la consente. La domanda breve e il riquadro del Nucleo dicono cosa è in attesa.
- **Limiti delle notifiche:**
  - Chromium senza interfaccia (i test) nega sempre le notifiche.
  - Nell'app desktop (Tauri, sospesa) la Web Notification API può non esserci: resta il conteggio nel titolo.
- **Test:**
  - `tests/agent_engine/test_approval_answers.py`: le parole riconosciute; la domanda; una run vera che si ferma, poi «sì» o «no» dall'orchestratore; la più vecchia per prima; un sì senza niente in attesa.
  - `frontend/tests/notify.test.tsx`: il titolo, la notifica che compare e si chiude, nessuna notifica davanti al riquadro, il bottone in APPROVAZIONI.

## Alternatives considered
- **Bottoni Consenti/Nega dentro la notifica:** servono un service worker e le Notification actions, che non esistono ovunque. Il clic che porta al Nucleo funziona in ogni browser.
- **Ripetere la domanda prima di decidere** («Confermi di eliminare vecchio.txt?»): più sicuro, ma è proprio la conversazione lunga che l'utente non vuole. La domanda la fa già la run quando si ferma.
- **Capire il sì e il no con il modello:** più flessibile, ma lento e costoso, e un errore di comprensione diventerebbe un'azione. Una lista chiusa di parole sbaglia per eccesso di prudenza: nel dubbio decide il motore.
