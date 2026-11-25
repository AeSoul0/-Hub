# ADR-021: Voce locale, nodo domotico MQTT e indice delle skill (M15)

## Status
**Accepted** (2026-10-24, decisioni dell'utente su voce, domotica e conferma delle azioni vocali; il resto su proposta di M15)

## Context
M15 chiude V1. ADR-019 aveva rinviato qui la voce: *"un solo percorso local-first (STT e TTS locali) che passa dal Gateway come ogni altro input"*. La mappa del codice ha trovato quanto segue.

- **Voce.** Ci sono due ingressi STT, `/api/orchestrator/listen` e la WebSocket `/ws/orchestrator`, tutti e due su Groq Whisper in cloud. Il TTS è edge-tts, anch'esso un servizio di rete. Il testo trascritto entra come un task scritto: niente distingue un comando vocale.
- **Domotica.** Non esiste codice.
- **Scelta dei tool.** `_build_model_tools` manda al Worker la definizione di *ogni* tool permesso, a ogni richiesta, con tutte le istruzioni delle skill: 8 tool oggi, 12 con la domotica. Il costo per caso cresce con il catalogo, e la latenza conta di più con la voce.

## Decision
1. **Voce locale** (decisione dell'utente): faster-whisper per STT e Piper per TTS, solo CPU, senza cloud e senza fallback cloud.
   - I modelli si scaricano al primo uso. `AEHUB_STT_MODEL` vale `base` di default; `AEHUB_TTS_VOICE` vale `it_IT-paola-medium`.
   - Senza modello, o se il motore fallisce, la risposta scritta arriva lo stesso, senza audio.
   - Groq ed edge-tts escono dal codice e dalle dipendenze.
2. **Un solo percorso vocale.** `app/voice/` trascrive e poi avvia la run con `input_channel="voice"`; HTTP e WebSocket chiamano la stessa funzione. Il testo trascritto è l'istruzione dell'utente, quindi passa dall'`InputGuardrail` come ogni task. Il canale viaggia nel task fino al Gateway, e la WebSocket smette di salvare file temporanei a mano.
3. **Azioni HIGH chieste a voce: sempre approvate a schermo** (decisione dell'utente), anche per l'admin e anche a contesto pulito. Il microfono sente anche una TV o un'altra persona. La regola sta in `PolicyEngine`, accanto a quella sul contenuto non fidato, e vale anche per i subagent di una run vocale.
4. **Nodo domotico su MQTT** (decisione dell'utente).
   - I dispositivi si dichiarano in un file JSON (`AEHUB_HOME_DEVICES`): id, nome, tipo (`light` o `lock`), topic di comando e formato (`zigbee2mqtt` o `tasmota`).
   - Broker in `AEHUB_MQTT_URL`; la password è un segreto del keyring (`AEHUB_MQTT_PASSWORD`).
   - Il rischio è per azione, quindi un tool per azione:
     - `home_list_devices`: LOW;
     - `home_set_light`: LOW;
     - `home_lock`: LOW, perché chiudere rende più sicuro;
     - `home_unlock`: HIGH con `requires_approval`.
   - Il modello sceglie solo l'id di un dispositivo dichiarato, mai un topic o un host: niente SSRF, e niente comandi verso dispositivi che l'utente non ha elencato.
   - Lo stato letto dai dispositivi non entra nel prompt in questa versione.
5. **Indice delle skill in un database separato** (richiesta dell'utente). È un file SQLite a sé (`AEHUB_SKILL_INDEX_PATH`), distinto dal database dell'app, con FTS5 (BM25) su nome, descrizione ed esempi dei tool.
   - **Quando sceglie:** all'inizio della run, *dal solo compito dell'utente*, sceglie i primi `AEHUB_TOOL_TOP_K` tool (6). La scelta resta salvata nella run e non cambia tra un turno e l'altro né al resume.
   - **Cosa vede il modello:** solo quei tool e le istruzioni delle loro skill.
   - **Cosa fa il Gateway:** rifiuta, senza eseguirla, una chiamata a un tool non esposto nella run. Così un'injection non può usare un tool che il compito non ha richiamato.
   - **Fallback:** se il catalogo non supera *k*, o l'indice è vuoto o in errore, si espone tutto come prima.
   - **Aggiornamento:** l'indice si ricostruisce quando cambia la firma del registry (nomi e descrizioni dei tool).
   - **Cosa conta per la scelta:** nome, descrizione e un campo nuovo `examples` di `ToolMetadata` (parole in italiano e inglese), che solo l'indice legge e che non arriva mai al modello. I termini del compito sono troncati in modo grezzo, quindi "documenti" e "documento" coincidono.
   - **Trovato durante M15:** le istruzioni delle skill (`system_prompt_extension`) non arrivavano al modello già da prima, perché `get_system_prompt_extensions` non la chiama nessuno. Restano fuori anche ora: le indicazioni necessarie stanno nelle descrizioni dei tool e nel loro output (ad esempio le citazioni di `search_documents`).
   - **Test ed eval:** la selezione è un livello di difesa a sé, quindi nei test parte spenta (`AEHUB_TOOL_SELECTION=off`) e ogni altro livello si prova da solo; la accendono i suoi test e il gate delle eval. I due casi storici di injection girano con la selezione spenta, per provare la sola provenienza, e due casi nuovi provano lo stesso attacco a selezione accesa.
   - **Risultato:** sul gate delle eval il costo medio per caso passa da $0.00888 a $0.00573 (−35%).
6. **Modulo legacy `app/core/database.py` eliminato** (richiesta dell'utente). Le sue tabelle erano scritte e mai lette:
   - `tasks` (`TaskManager`, una riga per chiamata di tool, già registrata nell'audit);
   - `chats`;
   - `settings` di sessione, lette e poi scartate, per cui i comandi `/precise`, `/creative`, `/deep` e `/fast` non hanno mai avuto effetto;
   - tre tabelle `memory_*`.

   Escono il modulo, `TaskManager` e quei comandi; resta `/stop`. Le tabelle già create in un database esistente restano lì, inerti.
7. **Distribuzione del desktop.**
   - Le chiavi dell'updater sono generate sulla macchina dell'utente, fuori dalla repo: la pubblica va in `tauri.conf.json`, la privata la carica l'utente nei secret della CI.
   - La firma Authenticode è un passo della CI che si attiva quando i secret del certificato ci sono.

## Trade-offs
- **Pro**
  - L'audio non esce dalla macchina e la voce funziona offline.
  - Un'azione vocale pericolosa non parte mai da sola.
  - La domotica parla solo con dispositivi dichiarati.
  - Meno token per richiesta.
  - Circa 1.500 righe di codice legacy in meno.
- **Contro**
  - Il primo uso della voce scarica i modelli: circa 150 MB per STT e 60 MB per TTS.
  - Su CPU la trascrizione richiede qualche secondo.
  - La scelta dei tool per parole chiave può non trovare un tool chiesto con parole diverse; per questo gli esempi di ogni tool sono in italiano e in inglese, e *k* lascia margine.
  - I comandi slash finti spariscono.

## Consequences
- Nuove dipendenze: `faster-whisper`, `piper-tts`, `paho-mqtt`. Escono `groq` ed `edge-tts`.
- `TaskExecutionContext` acquista `input_channel` ed `exposed_tools`.
- Nuovi casi di eval per comandi vocali, domotica e scelta dei tool. La baseline si aggiorna e il costo medio per caso deve scendere.
- Un broker MQTT di test (Mosquitto) gira come servizio nella CI.
