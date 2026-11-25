# ADR-024: Impostazioni della voce e voce cloud ElevenLabs opzionale (F3)

## Status
**Accepted** (2026-10-26, terza milestone della roadmap del frontend, F3)

## Context
ADR-021 ha reso la voce locale: faster-whisper per capire, Piper per parlare, nessun audio fuori dal computer. Modello, lingua e voce erano variabili d'ambiente (`AEHUB_STT_MODEL`, `AEHUB_STT_LANGUAGE`, `AEHUB_TTS_VOICE`): per cambiarle bisognava riavviare, e l'interfaccia non le mostrava. Inoltre:

- L'utente ha chiesto **ElevenLabs** come voce più naturale, **opzionale**.
- La risposta di una run chiesta a voce, se si fermava per un'approvazione, arrivava solo scritta.

## Decision
1. **Le impostazioni della voce si cambiano dal Control Plane, senza riavvio.** Sono nel gruppo `voice` di `/api/settings` (stesso meccanismo di M12: database, poi ambiente, poi default):
   - `AEHUB_STT_MODEL`, una scelta tra `tiny`, `base`, `small`, `medium`, `large-v3-turbo` e `large-v3`;
   - `AEHUB_STT_LANGUAGE`, una lingua oppure `auto`;
   - `AEHUB_TTS_ENGINE`, `piper` o `elevenlabs`;
   - `AEHUB_TTS_VOICE`, la voce Piper;
   - `AEHUB_ELEVENLABS_VOICE` e `AEHUB_ELEVENLABS_MODEL`, la voce e il modello di ElevenLabs.

   Le scelte si validano contro l'elenco. I nomi che finiscono in un percorso o in un URL si validano con un'espressione regolare (niente `../`, niente `/`). Il motore rilegge le impostazioni a ogni uso: un modello o una voce cambiati valgono dalla frase successiva, e il motore precedente si lascia andare.
2. **ElevenLabs è un motore opzionale e spento per default.**
   - La chiave `ELEVENLABS_API_KEY` sta nel portachiavi del sistema, come le altre: dall'app desktop con `PUT /api/desktop/secrets`, in Docker con `python scripts/aehub.py setup`. Non si rilegge mai.
   - Il testo della risposta va a `api.elevenlabs.io` (`POST /v1/text-to-speech/{voice_id}`); torna un MP3.
   - Il modello predefinito è `eleven_flash_v2_5`, il più rapido ed economico, con l'italiano.
3. **Piper parla ogni volta che il cloud non può.** Succede quando manca la chiave o la voce, quando ElevenLabs risponde con un errore o non risponde, e quando la risposta supera 2.500 caratteri, perché il costo è a carattere e una risposta lunga si legge meglio. Una risposta non resta mai muta per colpa del cloud.
4. **Il microfono resta locale con qualsiasi motore.** Con ElevenLabs esce il testo della risposta, mai l'audio di chi parla. L'interfaccia lo dice accanto alla scelta.
5. **Nuove API di gestione `/api/voice`.**
   - `GET /api/voice` mostra:
     - le impostazioni in uso;
     - se la chiave ElevenLabs c'è, senza mai il suo valore;
     - i modelli già scaricati, con il loro peso.
   - `GET /api/voice/elevenlabs/voices` è l'elenco delle voci dell'account. Gli id si filtrano con la stessa espressione regolare dell'impostazione.
   - `POST /api/voice/speak` dice un testo, al massimo 5.000 caratteri:
     - con `preview=true`, per l'anteprima delle Impostazioni, usa solo ElevenLabs e riporta l'errore vero;
     - senza `preview` è *best effort*, e il Nucleo lo usa per la risposta di una run ripresa.

   Nessuna di queste route riceve audio o avvia una run: la voce in ingresso resta un solo percorso (`/api/orchestrator/listen` e il WebSocket, ADR-019 e ADR-021). Il test della superficie API vieta ancora `/api/voice/stream`.
6. **Una run chiesta a voce risponde a voce anche dopo un'approvazione.**
   - L'evento `run.resumed` porta `input_channel`, letto dal compito salvato della run.
   - Quando vale `voice`, il Nucleo fa dire la risposta e la sfera segue il livello della voce.
7. **La pagina VOCE del Control Plane.** Contiene:
   - modello e lingua del riconoscimento, con il peso del download e la RAM indicativa;
   - il motore, con l'avviso sul testo che esce;
   - la voce Piper (suggerimenti, oppure un nome qualsiasi del catalogo);
   - per ElevenLabs: la chiave, l'elenco delle voci e il modello;
   - l'anteprima;
   - i modelli scaricati.

## Consequences
- Con il motore predefinito non cambia niente: tutto resta sul computer, come in ADR-021.
- Con ElevenLabs le risposte passano dai server di ElevenLabs, con le loro regole di conservazione (la *zero retention* è solo per i piani enterprise) e un costo per carattere.
- Il controllo della configurazione avvisa, senza bloccare, se è scelto ElevenLabs ma manca la chiave o la voce.
- `docs/frontend-coverage.md` nasce con questa milestone e traccia la copertura dell'interfaccia fino al 100% di F10.
