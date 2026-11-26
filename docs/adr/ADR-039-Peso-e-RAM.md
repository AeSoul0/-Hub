# ADR-039: Meno peso e meno RAM (O1)

## Status
**Accepted** (2026-11-26; roadmap O1, misure del 2026-11-25. L'utente ha un PC con 7,7 GB di RAM.)

## Context
Misure del 2026-11-25:

| Componente | RAM |
|---|---|
| Backend a riposo | 120–130 MB |
| PostgreSQL | circa 130 MB |
| Server del frontend | circa 100 MB, più circa 90 MB del processo `npm` |

- **L'embedder della memoria** usava `sentence-transformers`. All'import aggiungeva circa 750 MB (torch e transformers), più il modello. torch pesava anche sull'immagine Docker, con un passaggio apposta per la versione CPU.
- **Il frontend in Docker** partiva con `npm start`, che teneva in memoria `npm`, una shell e il server, e copiava nell'immagine tutto `node_modules`.
- **I modelli della voce** escono dalla RAM dopo `AEHUB_VOICE_IDLE_MINUTES` senza uso (F9). Il modello degli embedding invece restava caricato fino al riavvio.

## Decision
1. **Embedding su ONNX Runtime.**
   - Lo stesso modello (`all-MiniLM-L6-v2`, o quello in `AEHUB_EMBEDDING_MODEL`), dall'export ONNX che il repository di sentence-transformers pubblica (`onnx/model.onnx`), con il suo `tokenizer.json`.
   - Il vettore si calcola come fa sentence-transformers: media dei vettori dei token, escluso il padding, normalizzata a lunghezza 1, con i testi tagliati a 256 token.
   - Il nome resta `st:<modello>`: stesso modello e stessi vettori, quindi quelli già salvati continuano a valere.
   - Pacchetti: `onnxruntime`, `tokenizers`, `huggingface-hub`, `numpy`, già presenti per Whisper e Piper. Escono `torch` e `sentence-transformers`, anche dal dockerfile.
   - Un controllo della CI fallisce se torch torna nell'immagine.
   - Un modello senza export ONNX lo dice, e suggerisce `AEHUB_EMBEDDER=hash`.
2. **Un'impostazione sola per i modelli locali.**
   - `AEHUB_VOICE_IDLE_MINUTES` (VOCE) vale anche per il modello degli embedding: dopo quel tempo senza uso esce dalla RAM e si ricarica alla prima ricerca (circa 0,4 s).
   - SISTEMA lo elenca tra i modelli in memoria.
3. **Frontend in Docker con il server standalone di Next.**
   - Con `AEHUB_STANDALONE=1`, solo nel build dell'immagine, Next produce `server.js` con i soli moduli che servono.
   - L'immagine copia quello e i file statici, gira come utente `node` e parte con `node server.js`.
   - Una nuova fase della CI avvia l'immagine e controlla che il Nucleo risponda.

## Consequences
Misure su Linux, 2026-11-26:

| Cosa | Prima | Dopo |
|---|---|---|
| Embedder, RAM | circa 750 MB solo all'import, più il modello | +153 MB con il modello caricato; 85 MB dopo averlo liberato |
| Embedder, tempi | non misurati | caricamento 0,43 s, 2,6 ms per frase |
| Server del frontend, RAM | 142 MB in tre processi (npm 55, shell 2, server 85) | 84 MB in un solo processo |
| Server del frontend, file | `node_modules` di 551 MB | 42 MB |

- **Somiglianze come sentence-transformers.** Sulle tre frasi del README di sentence-transformers, l'embedder dà 0,666 / 0,1046 / 0,1411, gli stessi valori pubblicati per `all-MiniLM-L6-v2`.
  - Per la prova, i file del modello sono stati presi da un pacchetto npm che li ripubblica da `Xenova/all-MiniLM-L6-v2`, perché da qui Hugging Face non è raggiungibile.
  - Nell'uso normale il backend li scarica dal repository di sentence-transformers.
- **Test:**
  - `tests/agent_engine/test_embedder_onnx.py`: pooling, taglio a 256 token, nome, modello senza ONNX, rilascio dopo l'inattività;
  - `frontend/tests/system.test.tsx`: il nome dei modelli in memoria.
- **App desktop (sospesa):** parte ancora con l'embedder `hash`. Può passare a quello ONNX senza aggiungere pacchetti, quando la si riprende.
- **Resta da fare:**
  - un'immagine del backend più piccola, che oggi parte dall'immagine di Playwright con Chromium;
  - la misura delle immagini su Docker. La CI ora stampa la dimensione di entrambe.

## Alternatives considered
- **`fastembed`:** fa la stessa cosa, ma è una dipendenza in più, con un suo catalogo di modelli e una sua cache. Bastano le librerie già installate.
- **Il modello quantizzato int8:** più leggero, ma i vettori cambiano un po' e quelli salvati non varrebbero più allo stesso modo. Si può offrire come scelta in futuro, con un nome diverso.
- **Servire l'export statico dal backend anche in Docker,** come fa l'app desktop: toglierebbe un container, ma cambia porte, origini e avvio dello stack. Il server standalone è un cambio interno all'immagine.
