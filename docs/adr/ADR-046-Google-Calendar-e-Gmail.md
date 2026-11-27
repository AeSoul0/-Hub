# ADR-046: Google Calendar e Gmail (N4)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N4, il servizio scelto dall'utente: Google)

## Context
- N4 lasciava aperti calendario ed email, in attesa della scelta del servizio. L'utente ha scelto Google.
- ÆHub è per una persona sola, sul suo computer o nel suo Codespace. L'account da collegare è quello del proprietario, con un client OAuth che crea lui: nessun server di ÆHub in mezzo.
- Le chiavi non vanno mai in un file né nel database (ADR-020, ADR-038): portachiavi del sistema o variabili d'ambiente.

## Decision
1. **Il client OAuth del proprietario:**
   - **In Google Cloud Console:** un progetto con Google Calendar API e Gmail API attive. Schermata di consenso «Esterno», con il proprietario come utente di test. Un ID client «Applicazione web» con l'URI di reindirizzamento che STRUMENTI → Google mostra (`…/api/google/callback`, oppure `AEHUB_GOOGLE_REDIRECT_URI` dietro un proxy).
   - **Le chiavi:** `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` sono chiavi come le altre (launcher, app desktop, secret del Codespace).
2. **Collegamento** (`app/google/oauth.py`, `app/api/google.py`):
   - **Chi avvia:** solo il proprietario («Collega Google», un POST con controllo dell'origine).
   - **PKCE S256 e uno stato casuale:** lo stato vale 10 minuti e una sola volta. Il verificatore resta nel backend.
   - **Il ritorno:** Google rimanda il browser a `/api/google/callback`, che scambia il codice e torna su STRUMENTI con `?google=connected`.
   - **Permessi minimi:** `calendar.events`, `gmail.readonly`, `gmail.send`. Nessun accesso a Drive, ai contatti o all'eliminazione della posta.
3. **Il token dell'account:**
   - **Il refresh token:**
     - nell'app desktop va nel portachiavi del sistema;
     - con Docker o nel Codespace resta in memoria e la pagina lo mostra una volta sola, da salvare come `GOOGLE_REFRESH_TOKEN` (secret del Codespace, o `scripts/aehub.py setup`); al riavvio si legge da lì;
     - mai nel database o in un file.
   - **Il token di accesso** vive in memoria e si rinnova prima che scada. Se Google lo rifiuta, un nuovo tentativo; poi «ricollega da STRUMENTI».
   - **Scollega** revoca il token presso Google e lo dimentica (anche dal portachiavi). Se veniva da un secret, la pagina dice di toglierlo.
   - **Collegare e scollegare** finiscono nel registro di audit.
4. **Gli strumenti** (skill `google`, attraverso il Tool Gateway):
   - `calendar_list_events` (LOW): gli eventi dei prossimi giorni, con ricerca;
   - `calendar_create_event` (MEDIUM): un'ora di default, oppure giorni interi; l'ora è quella di questo computer;
   - `gmail_search` e `gmail_read` (LOW): la sintassi di Gmail; del messaggio si legge il testo semplice, altrimenti l'HTML senza tag;
   - `gmail_send` (HIGH): aspetta sempre l'approvazione; al massimo 10 destinatari, indirizzi controllati.
   - **Dati, non istruzioni:** quello che leggono eventi e posta l'hanno scritto altri, quindi `untrusted_output`. Dopo averlo letto, ogni azione HIGH chiede l'approvazione (ADR-036).
   - **Senza account collegato** gli strumenti rispondono come collegarlo.
5. **Chiamate dirette** alle API REST di Google con `httpx`, già presente: nessuna libreria nuova.

## Consequences
- Finché l'app resta «In test» su Google, il refresh token scade dopo 7 giorni: si ricollega da STRUMENTI, oppure si pubblica l'app (per un uso personale Google mostra un avviso «app non verificata»).
- Nel Codespace il collegamento sopravvive a un riavvio solo dopo aver salvato il token come secret.
- I comandi istantanei non toccano Google: ogni richiesta su calendario e posta passa dal motore e dal Critic.
- Non verificato con un account vero da qui: i test usano un Google finto (`httpx.MockTransport`). La prova vera la fa l'utente.
