# ADR-028: La casa dal Control Plane (F7)

## Status
**Accepted** (2026-10-30, settima milestone della roadmap del frontend, F7)

## Context
Il nodo domotico MQTT (M15, ADR-021) funziona nel motore, ma dall'interfaccia non si vedeva:

- **Dispositivi:** si dichiaravano solo in un file JSON da scrivere a mano, seguito da un riavvio.
- **Broker:** indirizzo e utente erano variabili d'ambiente, lette all'avvio.
- **Comandi:** partivano solo da una run, quindi passavano sempre da un modello.
- **Stato:** ÆHub non sapeva in che stato fosse un dispositivo.

## Decision
1. **Due nuove impostazioni senza riavvio**, con il meccanismo di M12: `AEHUB_MQTT_URL` e `AEHUB_MQTT_USERNAME`. Si leggono a ogni messaggio. La password resta un segreto del keyring (`AEHUB_MQTT_PASSWORD`): l'API dice solo se è impostata.
2. **Dispositivi dichiarati dal Control Plane.**
   - Stanno in una riga privata di `app_settings`, nello stesso formato del file e con le stesse regole di validazione.
   - Il database è fuori dalla portata dei tool dell'agente: è lo stesso motivo per cui il file deve stare fuori dalla cartella di lavoro. L'agente non può dichiarare un dispositivo su un topic a sua scelta.
   - Ogni modifica finisce nell'audit come `home.devices.update` prima di applicarsi.
   - Il file `AEHUB_HOME_DEVICES` continua a valere ed è mostrato in sola lettura. L'agente vede entrambe le liste. Un id che compare in tutte e due spegne i dispositivi e la pagina dice perché, invece di sceglierne uno in silenzio.
   - Gli strumenti della casa esistono solo se c'è almeno un dispositivo: dopo una modifica vengono riletti, senza riavvio.
3. **Un comando è il tool dell'agente, attraverso il Tool Gateway.** `POST /api/home/devices/{id}/command` non scrive direttamente sul broker: chiama `home_set_light`, `home_lock` o `home_unlock` con la stessa pipeline di una run (policy, schema, guardrail, audit). Un tool spento in STRUMENTI resta spento anche da qui.
4. **Aprire una porta da qui.** `home_unlock` è HIGH e nella pagina ha un secondo passaggio esplicito.
   - Senza conferma l'API risponde 428 e non crea nessuna richiesta di approvazione.
   - Con la conferma il Gateway apre la richiesta per quella chiamata esatta, e l'API la decide subito a nome di chi ha cliccato. L'approvazione resta registrata, con richiedente e decisore.
   - Alternativa scartata: mandare l'utente alla pagina Approvazioni. Chi ha appena cliccato "Apri" dovrebbe approvare sé stesso su un'altra pagina, e quel flusso è fatto per riprendere una run, che qui non esiste.
   - Le richieste a voce e quelle dell'agente non cambiano: aprono l'approvazione e aspettano.
5. **Stato di un dispositivo.** Due informazioni, tenute separate perché non valgono lo stesso:
   - **Ultimo comando**, dell'agente o dell'interfaccia. Dice cosa è stato inviato, non che il dispositivo abbia obbedito, e la pagina lo scrive. Vive in memoria, fino al riavvio.
   - **Stato letto**, solo su richiesta (`POST /api/home/devices/{id}/state`). Con Zigbee2MQTT ÆHub chiede su `<base>/get` e ascolta `<base>`; con Tasmota manda un messaggio vuoto su `cmnd/<nome>/POWER` e ascolta `stat/<nome>/POWER`. Vale anche uno stato *retained*. Se il topic ha un'altra forma, la pagina dice che non si può chiedere.

   Non c'è una sottoscrizione permanente: terrebbe aperta una connessione e un thread per una funzione che serve solo a pagina aperta.
6. **Prova del collegamento.** `POST /api/home/broker/check` si collega una volta e riporta il motivo di un errore, senza mai includere la password.
7. **Interfaccia CASA**, in italiano e nello stile del Nucleo: schede dei dispositivi con stato e comandi, aggiunta e modifica, broker con la prova del collegamento e la password (salvabile solo nell'app desktop, dove c'è il keyring; altrimenti `python scripts/aehub.py setup`).

## Consequences
- `tests/security/test_api_surface.py` elenca le nuove route. Un comando esegue un tool, ma solo attraverso il Gateway, ed è riservato all'admin come tutte le scritture di questa API.
- Un dispositivo con un id già presente nel file non si può aggiungere; se il conflitto nasce dopo, modificando il file, gli strumenti della casa si fermano finché non viene risolto.
- La copertura dell'interfaccia (`docs/frontend-coverage.md`) passa dall'80% all'84%.
- Le prove su un broker vero girano solo in CI (Mosquitto).
