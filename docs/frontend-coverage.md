# Copertura dell'interfaccia: quanto del backend si controlla dalla UI

Il tag `v1.0.0` arriva quando questa tabella è al **100%** (fine di F10, ROADMAP §5). Ogni milestone del frontend la aggiorna.

**Regole:**
- Una riga conta come coperta (✓) quando la funzione si usa o si cambia dall'interfaccia, il Nucleo o il Control Plane.
- Un parametro di avvio (porte, URL del database, cartelle dei dati) conta come coperto quando la pagina Sistema lo mostra in sola lettura.
- ◐ vuol dire parziale e conta mezzo: per esempio si vede ma non si cambia, o si cambia solo scrivendo JSON.

**Ultimo aggiornamento:** F4, modelli, chiavi e limiti (2026-10-26).
**Copertura:** 30 righe su 48, cioè **62,5%**.

## Conversazione e voce

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 1 | Comando scritto (`POST /api/orchestrator/ask`) | Nucleo, campo comando | ✓ | F1 |
| 2 | Comando a voce (`POST /api/orchestrator/listen`) | Nucleo, microfono | ✓ | F1 |
| 3 | Voce e testo via WebSocket (`/ws/orchestrator`) | stesso controllo di 1 e 2, per altri client (i Canali C1 e C2) | ✓ | F1 |
| 4 | Modello e lingua del riconoscimento vocale | Control Plane → VOCE | ✓ | F3 |
| 5 | Motore della voce (Piper o ElevenLabs), voce, modello, chiave | Control Plane → VOCE | ✓ | F3 |
| 6 | Anteprima della voce | Control Plane → VOCE | ✓ | F3 |
| 7 | Risposta a voce di una run chiesta a voce e ripresa dopo un'approvazione | Nucleo | ✓ | F3 |
| 8 | Modelli vocali già scaricati, con il peso | Control Plane → VOCE | ✓ | F3 |
| 9 | Voce accesa o spenta (`AEHUB_VOICE`) | lo stato si vede in VOCE; si cambia solo dall'ambiente | ◐ | F9 |

## Motore e run

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 10 | Eventi live del motore | Nucleo, pannello MOTORE → EVENTI | ✓ | F1 |
| 11 | Approvazioni: elenco e decisione | Nucleo; Control Plane → APPROVAZIONI | ✓ | F1, F2 |
| 12 | Run in corso contro i loro limiti; fermare una run | Nucleo → RUN; Control Plane → RUN | ✓ | F2 |
| 13 | Stop di tutte le run e ripresa | Nucleo, FERMA TUTTO; Control Plane → RUN | ✓ | F2 |
| 14 | Storico delle run con filtri | Control Plane → RUN | ✓ | F2 |
| 15 | Vista di una run e timeline | Control Plane → RUN → Dettagli | ✓ | F2 |
| 16 | Spesa e statistiche | Nucleo (chip del budget); Control Plane → RUN | ✓ | F2 |
| 17 | Albero dei sub-agenti e verdetti del Critic | — | — | F8 |
| 18 | Ruolo forzato (`AEHUB_FORCE_ROLE`) | IMPOSTAZIONI → Modelli predefiniti | ✓ | F4 |

## Modelli, chiavi e limiti

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 19 | Modelli per ruolo con failover (`AEHUB_MODEL_ROLES`) | IMPOSTAZIONI → Modelli per ruolo (editor, con l'elenco dei modelli di ogni provider) | ✓ | F4 |
| 20 | Modello del Critic | IMPOSTAZIONI → Modelli per ruolo e Modelli predefiniti | ✓ | M12, F4 |
| 21 | Prezzi dei modelli | IMPOSTAZIONI → Prezzi, anche dal listino di OpenRouter | ✓ | M12, F4 |
| 22 | Budget mensile, soglia di avviso, limiti per run | IMPOSTAZIONI | ✓ | M12 |
| 23 | Chiavi dei provider nel portachiavi del sistema | Primo avvio e IMPOSTAZIONI → Chiavi (app desktop) | ✓ | M14, F4 |
| 24 | Server locale compatibile OpenAI (`AEHUB_LOCAL_BASE_URL`, chiave) | IMPOSTAZIONI → Modelli predefiniti; Chiavi | ✓ | F4 |
| 25 | Circuit breaker dei provider | IMPOSTAZIONI → Motore | ✓ | F4 |
| 26 | Durata delle approvazioni | IMPOSTAZIONI → Budget e limiti | ✓ | F4 |
| 27 | Budget di contesto e snapshot | IMPOSTAZIONI → Motore | ✓ | F4 |

## Strumenti, skill e sicurezza

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 28 | Catalogo di tool e skill, con il rischio di ciascuno | — | — | F5 |
| 29 | Attivare e disattivare i tool (policy del workspace) | — | — | F5 |
| 30 | Skill `SKILL.md` scaricate da internet | — | — | F5 |
| 31 | Server MCP consentiti | — | — | F5 |
| 32 | Selezione dei tool (indice delle skill) | — | — | F5 |
| 33 | Cartelle consentite ai tool | il Setup mostra la cartella di lavoro, che però si sceglie dal launcher | ◐ | F5 |
| 34 | Registro di audit | Control Plane → SICUREZZA | ✓ | M11 |

## Memoria e documenti

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 35 | Memoria: elenco, preferenze, cancellazione | Control Plane → MEMORIA | ✓ | M11 |
| 36 | Memoria accesa o spenta, embedder, soglia di somiglianza | — | — | F6 |
| 37 | Indice dei documenti e sincronizzazione (`/api/documents`) | — | — | F6 |
| 38 | Dimensione massima dei documenti | — | — | F6 |

## Casa

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 39 | Dispositivi e rischio di ogni azione (`home.json`) | — | — | F7 |
| 40 | Broker MQTT | — | — | F7 |

## Sistema

| # | Funzione del backend | Nell'interfaccia | Stato | Milestone |
|---|---|---|---|---|
| 41 | Accesso e uscita | schermata di accesso; Esci | ✓ | M11 |
| 42 | Primo avvio | Control Plane → Primo avvio | ✓ | M12, F4 |
| 43 | Stato di database, sidecar, bus degli eventi e aggiornamenti | — | — | F9 |
| 44 | Parametri di avvio in sola lettura (database, Redis, bus, host, origini, cartelle dei dati e dei modelli) | — | — | F9 |
| 45 | Flight recorder: ricerca ed esportazione | — | — | F9 |
| 46 | Eval dall'interfaccia | — | — | F9 |
| 47 | Rotazione della chiave di accesso | — | — | F9 |
| 48 | RAM dei componenti | — | — | F9 |

## Storia

| Milestone | Righe coperte | Copertura |
|---|---|---|
| F3 (prima versione della tabella) | 24,5 su 48 | 51% |
| F4 | 30 su 48 | 62,5% |
