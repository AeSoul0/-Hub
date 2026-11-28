# Guida d'uso di ÆHub

ÆHub è un assistente che lavora sul tuo computer: gli chiedi qualcosa a voce o per scritto, e Aurora (il suo motore) lo fa con gli strumenti che gli hai dato. Prima di fare qualcosa di rischioso, chiede a te.

Questa guida è per l'uso di tutti i giorni. Per installarlo leggi il [README](../README.md).

**Su Windows** si avvia con un doppio clic su `AEHub.cmd` (nella cartella di ÆHub) o, dopo il primo avvio, sull'icona **ÆHub** del desktop: avvia Docker Desktop se serve, aspetta che ÆHub sia pronto e apre il browser. Per fermarlo: `AEHub.cmd -Stop`.

---

## 1. Le due schermate

- **Il Nucleo** (la pagina iniziale) è dove parli con Aurora. Al centro c'è la sfera: cambia mentre ascolta, pensa, usa uno strumento o risponde.
  - A sinistra, la **conversazione**.
  - A destra, gli **eventi** e le **run**: ogni comando è una run, con il suo costo e il suo tempo.
- **Il Control Plane** (in alto a destra, «Control Plane») contiene le impostazioni e le pagine di controllo: APPROVAZIONI, RUN, STRUMENTI, VOCE, MEMORIA, DOCUMENTI, IMPOSTAZIONI e le altre.

La prima volta entri con la **chiave di accesso**: la stampa `python scripts/aehub.py login-key`, o nel Codespace `bash scripts/codespace.sh key`.

---

## 2. Parlare con Aurora

- **Per scritto:** scrivi nel campo in basso e premi INVIA.
- **A voce:** premi il microfono, oppure la barra spaziatrice, parla e premi di nuovo per inviare.
- **Senza toccare niente:** scegli una parola di attivazione nella pagina VOCE («Hey Jarvis», «Alexa», «Hey Mycroft»). Il Nucleo ascolta solo quella parola. Dopo la parola registra il comando e si ferma da solo quando smetti di parlare. Prima della parola non registra e non invia niente.

Puoi mandare **più comandi uno dopo l'altro** senza aspettare: ognuno ha la sua «luna» attorno alla sfera, e le risposte arrivano nella conversazione man mano.

### Cose che fa subito, senza pensarci

Sono comandi semplici: partono in un attimo e la risposta dice «istantaneo».

| Di' o scrivi | Cosa succede |
| --- | --- |
| «Apri Spotify», «apri la cartella Download» | apre l'app o la cartella (quelle che elenchi in IMPOSTAZIONI → App) |
| «Alza il volume», «pausa», «prossima canzone» | i tasti multimediali del computer |
| «Blocca lo schermo», «fai uno screenshot» | blocca il PC, salva uno screenshot nella cartella di lavoro |
| «Timer di 5 minuti», «ricordami alle 18 di chiamare Marco» | alla scadenza il Nucleo suona e, se sei su un'altra finestra, arriva una notifica |
| «Accendi la luce della cucina» | i dispositivi di casa configurati in CASA |

Nel Codespace i comandi del computer (app, volume, schermo) non ci sono, perché ÆHub non è sul tuo PC.

### Cose per cui ragiona

Tutto il resto va al motore: risponde il modello, e un secondo modello, il Critic, controlla la risposta.

- **Domande e ricerche:** «Che tempo fa a Lisbona questo weekend?», «cerca le ultime notizie su…».
- **I tuoi documenti:** «Cosa dice il contratto sull'affitto?». Risponde con le fonti citate. Clicca una citazione per leggere il passaggio.
- **I tuoi file:** «Trova le fatture di ottobre», «riassumi il PDF della riunione», «sposta le foto vecchie in Archivio».
- **Calendario e posta**, se hai collegato Google (vedi il punto 7): «Cosa ho domani?», «aggiungi dentista giovedì alle 15», «c'è una mail di Anna?».
- **Compiti lunghi:** «Trova le fatture, riassumile e scrivi un report». Aurora scrive prima un **piano** a passi. Nel pannello RUN vedi ogni passo: da fare, in corso, fatto.

Mentre il modello scrive, la risposta compare come **bozza**. Diventa definitiva quando il Critic l'ha controllata.

---

## 3. Le approvazioni

Le azioni rischiose (eliminare o sovrascrivere un file, mandare una email, aprire una serratura, eseguire un comando) **si fermano finché non decidi tu**.

- Aurora fa una domanda breve, per esempio «Posso eliminare vecchio.txt? Sì o no.».
- Rispondi **«sì»** o **«no»**, a voce o per scritto, oppure usa i pulsanti nel Nucleo o nella pagina APPROVAZIONI.
- Per **eliminare o sovrascrivere** un file serve **«sì, elimina»** (o «sì, sovrascrivi»): un «sì» semplice non basta.
- Se ÆHub non è in primo piano, una notifica del sistema e il titolo della scheda ti avvisano che una richiesta aspetta.

Quello che gli agenti eliminano non sparisce: va nel **cestino**, in STRUMENTI → Cestino, e si può ripristinare per 30 giorni.

---

## 4. Fermare

- **Una run:** nel pannello RUN, «Ferma la run».
- **Tutto:** in alto, «FERMA TUTTO» (cliccalo due volte). Le run in corso si fermano e le nuove non partono finché non premi «RIPRENDI».

Una run fermata lo dice nella conversazione («Comando fermato.»).

---

## 5. Le conversazioni

- Nel pannello di sinistra, la scheda **CRONOLOGIA** elenca le conversazioni passate. Puoi cercare nei comandi e nelle risposte.
- Cliccane una per **continuarla**: Aurora ricorda quella conversazione, non le altre.
- **«Nuova conversazione»** riparte da zero.

Se vai su un'altra pagina e torni, la conversazione è ancora lì, anche con le risposte arrivate nel frattempo.

---

## 6. Le cartelle

- **La cartella di lavoro** è il posto principale dove Aurora legge e scrive. Lì finiscono screenshot e caricamenti.
- **Altre cartelle:** in STRUMENTI → Confini aggiungi le cartelle che gli agenti possono usare, per esempio i tuoi Documenti.
- **Cosa resta sempre fuori:** i file di ÆHub, i file nascosti (come `.ssh` o `.env`) e AppData.
- **La ricerca nei documenti** copre la cartella di lavoro e le cartelle che hai aggiunto. In DOCUMENTI vedi cosa è indicizzato e puoi aggiornarlo.

---

## 7. Voce, memoria e Google

- **VOCE:**
  - accendi o spegni la voce e scegli quale voce legge le risposte (Piper, sul computer, oppure una voce online con la sua chiave);
  - scegli la lingua del riconoscimento e la parola di attivazione;
  - «Anteprima» fa sentire la voce.
- **MEMORIA:**
  - Aurora ricorda fatti, preferenze e regole tra una conversazione e l'altra;
  - qui li vedi, li correggi, ne aggiungi e li fai dimenticare;
  - per l'italiano c'è un modello multilingue, più preciso.
- **Google**, in STRUMENTI → Google:
  - collega il tuo Calendar e Gmail, seguendo i passi che la pagina mostra;
  - leggere è sicuro e creare un evento è a rischio medio;
  - **mandare una email aspetta sempre il tuo sì**.

---

## 8. Costi e limiti

- In alto nel Nucleo vedi quanto hai speso questo mese, rispetto al budget.
- Ogni run ha dei limiti: costo, tempo, errori, file modificati. Le barre del pannello RUN mostrano quanto manca.
- Quando un limite o il budget finisce, la run si ferma da sola e te lo dice.
- I limiti e il budget si cambiano in IMPOSTAZIONI.
- Con i modelli locali (Ollama) non si spende niente, ma sono più lenti.

---

## 9. Se qualcosa non va

| Succede | Cosa fare |
| --- | --- |
| «Manca la chiave di un provider» | aggiungi una chiave di un modello (o usa Ollama); IMPOSTAZIONI mostra cosa manca |
| Nel Codespace un comando ci mette minuti | è normale con i modelli locali su 2 processori: una macchina da 4 è circa due volte più veloce |
| «La connessione si è interrotta, ma ÆHub sta ancora lavorando» | aspetta: la risposta arriva comunque nella conversazione |
| Il Critic boccia spesso le risposte | in IMPOSTAZIONI scegli per il Critic un modello più capace |
| Il microfono non va | il browser deve avere il permesso del microfono; nel Codespace l'indirizzo è HTTPS, quindi funziona |
| Non sai cosa sta facendo | pannello RUN → Timeline, oppure «Dettagli →» per tutta la run |

La pagina SISTEMA mostra lo stato dei servizi, i registri e gli aggiornamenti.
