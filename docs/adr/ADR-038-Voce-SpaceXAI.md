# ADR-038: La voce SpaceXAI (xAI)

## Status
**Accepted** (2026-11-26, richiesta dell'utente: "aggiungi l'opzione di usare SpaceXAI TTS per connettermi all'API", con due voci fisse e la lingua sempre indicata)

## Context
- **Le voci disponibili:**
  - Piper, sul computer;
  - ElevenLabs, nel cloud, opzionale (ADR-024).
- **Cosa ha scelto l'utente:** SpaceXAI TTS, cioè l'API di sintesi vocale di xAI (`https://api.x.ai/v1/tts`).
  - **Prezzo:** a consumo, 15 $ per milione di caratteri, senza abbonamento.
  - **Voci:** `eve` (energica e allegra, accento britannico) e `altair` (formale, elegante, "premium").
  - **Lingue:** inglese, italiano e francese, sempre con il codice e mai `auto`.
- **Costo stimato,** con risposte da circa 500 caratteri:

  | Risposte al giorno | Al mese |
  |---|---|
  | 10 | circa 2,25 $ |
  | 60-65 | circa 15 $ |
  | 100 | circa 22,50 $ |

  Il costo del modello che scrive le risposte è a parte.

## Decision
1. **Un terzo motore,** `AEHUB_TTS_ENGINE=spacexai`.
   - `AEHUB_SPACEXAI_VOICE` accetta solo `eve` (predefinita) o `altair`.
   - `AEHUB_SPACEXAI_LANGUAGE` accetta solo `it` (predefinita), `en` o `fr`: un altro valore, `auto` compreso, viene rifiutato.
   - La chiave è `XAI_API_KEY`, nel portachiavi del sistema come le altre:
     - dall'app desktop con `PUT /api/desktop/secrets`;
     - altrimenti con `python scripts/aehub.py setup`, poi passata a Docker.
2. **La richiesta:** `POST /v1/tts` con `Authorization: Bearer`, e nel corpo:
   - `text`, `voice_id`, `language`;
   - `output_format` con codec `mp3`, 24 kHz, 128 kbit/s.

   La risposta è l'audio stesso.
3. **Come ElevenLabs:**
   - **Piper di riserva.** Parla Piper quando:
     - manca la chiave;
     - SpaceXAI risponde con un errore;
     - la risposta supera 2.500 caratteri (`MAX_CLOUD_CHARS`), anche per non pagare un testo lungo che è meglio leggere.
   - **L'anteprima** in VOCE mostra l'errore vero, senza passare a Piper.
   - **Avviso:** il controllo della configurazione avvisa se è scelta SpaceXAI senza chiave (`voice_spacexai_key_missing`).
4. **Lingua e costi:**
   - La lingua della voce è quella scelta, e l'avviso di ADR-034 la confronta con l'interfaccia.
   - La pagina VOCE mostra il prezzo e la stima mensile.
   - Il registro del backend annota i caratteri e il costo di ogni frase.

## Consequences
- **Dove va il testo:** il testo delle risposte lette ad alta voce va ai server di xAI; il microfono resta locale.
- **Non verificato dal vivo.** Da qui `api.x.ai` e la sua documentazione non sono raggiungibili, e non c'è una chiave.
  - Il formato della richiesta viene da un'integrazione open source che usa la stessa API (Home Assistant, `ha-spacexai`).
  - Va provato con la chiave vera, con l'anteprima in VOCE.
- **Test:**
  - `tests/agent_engine/test_voice_spacexai.py`;
  - `frontend/tests/voice.test.tsx`: la scelta del motore, la voce, la lingua, la chiave e la stima.

## Alternatives considered
- **Tutto il catalogo di voci (`GET /v1/tts/voices`):** l'utente ne vuole due fisse. Un elenco chiuso evita anche una chiamata in più.
- **Streaming via WebSocket:** riduce la latenza della prima parola, ma l'orchestratore oggi restituisce l'audio intero, come per Piper ed ElevenLabs.
- **Un contatore mensile dei caratteri nel database:** utile, ma per ora bastano la stima nella pagina e il registro. Si può aggiungere se l'uso cresce.
