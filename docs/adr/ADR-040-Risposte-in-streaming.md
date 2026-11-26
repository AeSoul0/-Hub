# ADR-040: Risposte in streaming e voce frase per frase (N1)

## Status
**Accepted** (2026-11-26; Roadmap 2, punto N1, richiesto dall'utente)

## Context
- **Prima la risposta arrivava tutta insieme.** Il modello la scriveva per intero, il Critic la controllava, la voce la sintetizzava tutta. Solo dopo compariva e si sentiva qualcosa.
- **Su una risposta lunga** l'attesa era di molti secondi con la chat vuota. Il tempo vero non cambia, ma l'attesa pesa.
- **Due vincoli da rispettare:**
  - il Critic controlla sempre la risposta;
  - il filtro di uscita (`OutputGuardrail`) toglie quello che non deve uscire.

  Niente di non controllato deve diventare la risposta, né essere letto ad alta voce.

## Decision
1. **Bozza mentre il modello scrive.**
   - Il Nucleo manda i comandi con `delivery=live`. L'orchestratore apre una `DraftStream` (`agent_engine/streaming.py`) e l'adapter chiede la risposta in streaming (`pydantic_ai.direct.model_request_stream`).
   - Il testo scritto finora va sullo stream dell'area di lavoro come `answer.delta`, al massimo ogni 80 ms.
   - Nel Nucleo compare come «bozza · in verifica», più chiara.
   - **Quando la bozza si cancella** (`answer.reset`):
     - il turno finisce con la chiamata di uno strumento: quel testo non era la risposta;
     - il Critic rimanda indietro la risposta.
   - **Fuori dalla bozza:** il Critic e i subagenti non ci scrivono mai (`streaming_answer(None)`).
   - **Provider senza streaming:** si richiede senza, e il risultato non cambia.
2. **La risposta resta quella controllata.** Quando il Critic accetta, la risposta della richiesta, già passata dal filtro, sostituisce la bozza. È l'unica che resta nella chat e l'unica che si sente.
3. **Voce frase per frase.**
   - Con `delivery=live` la risposta non porta audio (`speak: "sentences"`): il Nucleo la divide in pezzi (`splitSentences`):
     - frasi intere;
     - meno di 40 caratteri, si uniscono alla frase dopo;
     - oltre 280 caratteri, si tagliano a una virgola.
   - **Come si legge:**
     - ogni pezzo si chiede a `/api/voice/speak`;
     - il pezzo dopo si prepara mentre suona quello prima (`speakInSentences`);
     - una risposta nuova ferma la voce della vecchia.
   - **Risposte lunghe:** la richiesta porta `reply_chars`, la lunghezza di tutta la risposta. Oltre il limite del cloud (2.500 caratteri) parla Piper, come prima.
   - Anche la risposta di una run ripresa dopo un'approvazione si legge così.

## Consequences
- **Prova nell'app vera,** con un modello finto compatibile OpenAI che scrive una parola ogni 120 ms e un Critic che risponde in 0,8 s:
  - la bozza compare dopo 2,3 s dall'invio;
  - la risposta controllata arriva dopo 5,8 s.

  Prima, per 5,8 s la chat restava vuota.
- **Voce:** il primo suono arriva dopo la sintesi della prima frase, non di tutta la risposta. La voce parte comunque dopo il Critic: leggere la bozza aggirerebbe il controllo e il filtro.
- **Test:**
  - `tests/agent_engine/test_streaming.py`: adapter con modello in streaming, reset con uno strumento, provider senza streaming, Critic e subagenti fuori dalla bozza, `delivery`, Piper per le risposte lunghe;
  - `frontend/tests/streaming.test.tsx`: divisione in frasi, coda della voce, bozza nel Nucleo.

## Alternatives considered
- **Leggere ad alta voce la bozza:** la prima parola arriverebbe prima, ma si sentirebbe testo non controllato, anche quello che il filtro avrebbe tolto. Scartato.
- **SpaceXAI via WebSocket:** rimandato. Da qui l'API non è raggiungibile per provarla, e la voce frase per frase dà già quasi tutto il guadagno.
- **Audio in streaming sullo stream degli eventi:** più complesso, e `/api/voice/speak` per frase funziona già con tutti i motori, ripiego su Piper compreso.
