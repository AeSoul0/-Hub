# ADR-041: Parola di attivazione nella pagina (N2)

## Status
**Accepted** (2026-11-26; Roadmap 2, punto N2, richiesto dall'utente)

## Context
- **Prima bisognava premere** il microfono o la barra spaziatrice per dare un comando a voce.
- **L'utente ha scelto** di partire con una parola già pronta di openWakeWord. «Aurora» si potrà usare più avanti con un proprio modello, senza cambiare codice.
- **Vincoli:**
  - niente audio salvato né inviato prima della parola;
  - spenta di default;
  - leggera, perché il PC ha 7,7 GB di RAM;
  - niente servizi esterni.

## Decision
1. **Riconoscimento nel browser.**
   - La pagina del Nucleo esegue la pipeline di openWakeWord con onnxruntime-web 1.31.1 (WebAssembly, un solo thread):
     - il microfono viene ricampionato a 16 kHz (`Resampler`);
     - ogni 80 ms, il melspettrogramma degli ultimi campioni;
     - dagli ultimi 76 frame, un embedding di 96 valori;
     - dagli ultimi 16 embedding, il punteggio della parola (`WakePipeline` in `lib/nucleo/wake.ts`).
   - L'audio non esce dalla pagina finché la parola non viene sentita: non va nemmeno al backend.
   - Il motore si carica solo con una parola scelta (import dinamico).
2. **Il backend consegna i modelli:** `GET /api/voice/wake/{model}` (`app/voice/wake.py`).
   - **Modelli serviti:** solo i due modelli delle caratteristiche (`melspectrogram`, `embedding_model`) e la parola scelta.
   - **Parole pronte** (`hey_jarvis`, `alexa`, `hey_mycroft`): scaricate una volta dalla release v0.5.1 di openWakeWord e controllate con la SHA-256 fissata, prima di salvarle e prima di servirle.
   - **«aurora»:** è un file dell'utente, in `<AEHUB_VOICE_MODELS_DIR>/wake/aurora.onnx`. Se manca, la risposta dice dove metterlo e il controllo della configurazione avvisa (`voice_wake_model_missing`).
3. **Impostazioni:** `AEHUB_WAKE_WORD` (`off` di default) e `AEHUB_WAKE_SENSITIVITY` (`low`/`medium`/`high`, soglia 0,7, 0,5 o 0,35).
   - Si cambiano dalla pagina VOCE (sezione «Parola di attivazione»).
   - `GET /api/interface` le passa a ogni pagina, che si aggiorna subito.
   - Con la voce spenta il Nucleo non ascolta.
4. **Nel Nucleo:**
   - **Quando sente la parola:**
     - un suono breve;
     - poi registra come con il bottone;
     - la registrazione finisce da sola (`CommandEndWatch`): 1,2 s di silenzio dopo il parlato, 6 s senza parlare, oppure 20 s in tutto;
     - poi `/api/orchestrator/listen` con `delivery=live` (N1).
   - **Pausa dell'ascolto:** mentre registra, invia o parla. La risposta letta non può risvegliarlo, e riparte da audio nuovo.
   - **Pausa tra due attivazioni:** 2 s.
   - **Indicatore sotto la barra:**
     - in ascolto;
     - in pausa;
     - «tocca la pagina» se il browser tiene l'audio sospeso;
     - errore con il motivo.
5. **CSP delle pagine servite dal backend:** `script-src` aggiunge `'wasm-unsafe-eval'`. Permette di compilare WebAssembly, non `eval()`.
   - **ScriptProcessorNode invece di AudioWorklet:** un worklet è un modulo caricato da un URL, e la CSP e l'export statico lo rendono fragile.

## Consequences
- **Stessi punteggi di openWakeWord.** Con gli stessi campioni a 16 kHz e i modelli veri, i punteggi della pipeline TypeScript coincidono con quelli della libreria Python openwakeword 0.6.0: differenza massima 3·10⁻⁶ dopo il riscaldamento. «Hey jarvis» sintetico (espeak-ng) arriva a 0,995; una frase italiana senza la parola a 0,001.
- **Prova nell'app vera** (Chromium, con un file audio al posto del microfono: 3 s di silenzio, «hey jarvis», poi «accendi la luce della cucina»):
  - in ascolto dopo 3,3 s dall'apertura;
  - parola sentita circa 1 s dopo che è stata detta;
  - comando registrato e finito da solo;
  - `/listen` chiamato con `delivery=live`;
  - risposta mostrata e ascolto ripreso.
  - Con 13 s di frasi italiane senza la parola: nessuna attivazione.
- **Costo misurato qui** (Chromium headless, senza GPU):
  - circa 13% di un core in più, di cui circa 6% per i modelli (misurati da soli);
  - circa 130–200 MB di RAM in più nel processo della pagina, quasi tutti del motore WebAssembly. Le opzioni di memoria di onnxruntime non cambiano la cifra.
  - Si paga solo con una parola scelta e il Nucleo aperto.
  - Il file `.wasm` (15 MB) entra nell'immagine del frontend e nell'export statico, ma si scarica solo quando serve.
- **Test:**
  - `tests/agent_engine/test_wake_word.py`: impostazioni, hash fissati, download una volta e controllato, cosa serve la rotta, «aurora», interfaccia e avviso;
  - `frontend/tests/wake.test.tsx`: pipeline con modelli finti, ricampionamento, soglia e pausa, fine del comando, flusso nel Nucleo;
  - `frontend/tests/voice.test.tsx`: la sezione della pagina VOCE.
- **Non verificato:** un microfono e una voce veri sul PC dell'utente. Le parole pronte sono in inglese: con un accento italiano la sensibilità può andare alzata.

## Alternatives considered
- **Riconoscimento nel backend** (audio inviato continuamente via WebSocket, onnxruntime Python già caricato): meno RAM nel browser. Però l'audio uscirebbe sempre dalla pagina, anche dal telefono in LAN. Scartato.
- **Vosk con grammatica di una sola parola:** riconosce «Aurora» senza addestramento, ma pesa di più (modello italiano e libreria) e non è una vera parola di attivazione. Non scelto dall'utente.
- **Addestrare «Aurora» qui:** ore di calcolo e qualità incerta senza provarlo sul PC. Rimandato: basta mettere il file e scegliere «aurora».
- **AudioWorklet:** più moderno, ma richiede un modulo servito come file a parte (vedi decisione 5).
