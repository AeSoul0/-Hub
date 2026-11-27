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
   - Lo stesso modello `all-MiniLM-L6-v2`, dal suo export ONNX in fp32 (`onnx/model.onnx`), con il suo `tokenizer.json`.
   - **Download fissato:** l'export viene da `Xenova/all-MiniLM-L6-v2` al commit `751bff37…`, e ogni file è controllato con il suo SHA-256 prima di usarlo.
     - Un altro modello in `AEHUB_EMBEDDING_MODEL` si indica con il suo commit, `owner/nome@<commit>`. Mai "quello che c'è oggi su main".
     - Lo chiede anche bandit (B615) in CI.
     - Uno script della CI (`scripts/check_embedding_pin.py`) verifica sul hub che commit e hash esistano.
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
  - Nell'uso normale il backend scarica gli stessi file, dallo stesso commit, e ne controlla l'hash.
- **Test:**
  - `tests/agent_engine/test_embedder_onnx.py`: pooling, taglio a 256 token, nome, modello senza ONNX, rilascio dopo l'inattività;
  - `frontend/tests/system.test.tsx`: il nome dei modelli in memoria.
- **App desktop (sospesa):** parte ancora con l'embedder `hash`. Può passare a quello ONNX senza aggiungere pacchetti, quando la si riprende.
- **Fatto in N8 (sotto):** l'immagine del backend più piccola e la misura delle immagini e dello stack su Docker.

## Alternatives considered
- **`fastembed`:** fa la stessa cosa, ma è una dipendenza in più, con un suo catalogo di modelli e una sua cache. Bastano le librerie già installate.
- **Il modello quantizzato int8:** più leggero, ma i vettori cambiano un po' e quelli salvati non varrebbero più allo stesso modo. Si può offrire come scelta in futuro, con un nome diverso.
- **Servire l'export statico dal backend anche in Docker,** come fa l'app desktop: toglierebbe un container, ma cambia porte, origini e avvio dello stack. Il server standalone è un cambio interno all'immagine.

## N8: immagine del backend più leggera (2026-11-27)

### Decision
1. **Base Python 3.12 slim** (`python:3.12-slim-bookworm`) invece dell'immagine di Microsoft Playwright, che porta Chromium, Firefox, WebKit e le loro librerie di sistema.
2. **Il browser solo se serve:**
   - si costruisce con `AEHUB_BROWSER=1`, dal `.env` principale (`docker compose build backend`);
   - allora l'immagine installa il pacchetto Playwright (`requirements-browser.txt`, tolto da `requirements.txt`), la sola *headless shell* di Chromium con le sue librerie, e `libatomic1` per il Node di Playwright;
   - senza (il predefinito) la skill browser non offre il suo strumento (`browser_available()`), quindi il modello non propone un browser che non c'è. La ricerca web resta.
   - Fuori da Docker (Codespace, app desktop, sviluppo) Playwright si installa come prima, con `requirements-browser.txt`.
3. **Healthcheck con Python** (`urllib`), perché l'immagine slim non ha curl: nel dockerfile e in `docker-compose.yaml`.
4. **CI:** costruisce l'immagine senza browser (la skill non offre strumenti) e quella con il browser. In quella con il browser, Chromium deve partire e leggere una pagina, e la skill deve offrire il suo strumento. Stampa la dimensione di entrambe.

### Misure (Docker 29 su Linux, 2026-11-27)

| Cosa | Prima (immagine Playwright) | Dopo (slim, senza browser) |
|---|---|---|
| Immagine del backend | 4,87 GB | 1,20 GB |
| Ambiente Python (`/opt/venv`) | — | 740 MB (era 907 MB con Playwright) |
| Backend dopo l'import e le skill | 100 MB | 100 MB |

Lo stack avviato (backend slim, PostgreSQL con pgvector, Redis), a riposo dopo l'avvio:

| Container | RAM |
|---|---|
| Backend | 95 MB |
| PostgreSQL | 38 MB |
| Redis | 4 MB |

- **La RAM non cambia:** Chromium occupa memoria solo quando la skill lo usa. Il guadagno è il disco e il download (3,7 GB in meno) e una build più rapida.
- **Il frontend** resta come in O1: 42 MB di file, circa 84 MB di RAM. Con il backend e i servizi lo stack sta sotto i 250 MB a riposo, sui 7,7 GB del PC dell'utente.
- **Il più grande** ora sono le librerie della voce e dei modelli locali: PyAV di faster-whisper (130 MB), CTranslate2 (85 MB), ONNX Runtime (80 MB), Piper (47 MB). Servono alla voce locale e restano.
- **Non misurata da qui:** l'immagine con il browser, perché questa sessione non raggiunge i mirror Debian (`deb.debian.org`). La costruisce e la prova la CI; la stima è di circa +400 MB.

