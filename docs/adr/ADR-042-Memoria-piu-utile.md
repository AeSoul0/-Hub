# ADR-042: Memoria più utile (N3)

## Status
**Accepted** (2026-11-27; Roadmap 2, punto N3, richiesto dall'utente)

## Context
- **Documenti:** la ricerca con fonti citate guardava solo la cartella di lavoro, non le cartelle scelte per gli agenti (F11).
- **Lingua:** il modello degli embedding (all-MiniLM-L6-v2) è addestrato sull'inglese, quindi in italiano trova i ricordi per significato peggio.
- **Comandi indipendenti:** ogni comando era una run a sé. Una domanda di seguito («e domani?») trovava il turno prima solo se le parole coincidevano, e gli episodi di una conversazione lunga si accumulavano uno per uno.
- **Vincoli:**
  - niente servizi esterni;
  - poca RAM (7,7 GB sul PC);
  - modelli scaricati solo se fissati a un commit con la SHA-256 di ogni file (ADR-039).

## Decision
1. **Cartelle degli agenti nell'indice dei documenti** (`app/documents/index.py`):
   - **Cosa entra:** l'indice copre la cartella di lavoro e le cartelle di `AEHUB_AGENT_FOLDERS`.
   - **Nomi nelle citazioni:**
     - un file della cartella di lavoro si chiama come prima, con il percorso dentro la cartella;
     - un file di una cartella degli agenti si chiama con il percorso completo, così la citazione dice dov'è.
   - **Niente doppioni:**
     - una cartella degli agenti dentro quella di lavoro non si indicizza due volte;
     - un file raggiungibile da due cartelle entra una volta sola.
   - **Limiti e regole:** gli stessi di prima (2000 file, file nascosti esclusi, link simbolici che escono dalla cartella esclusi).
   - **Senza cartella di lavoro:** le cartelle degli agenti si indicizzano lo stesso.
   - **Pagina DOCUMENTI:** le elenca, ognuna con il suo stato.
2. **Modello multilingue fissato:** `paraphrase-multilingual-MiniLM-L12-v2`.
   - **Versione:** l'esportazione ONNX int8 di Xenova al commit `2c4055b1…`, con le SHA-256 di `onnx/model_quantized.onnx` e `tokenizer.json`.
   - **Peso:** circa 120 MB invece dei circa 470 MB della versione fp32.
   - **Compatibilità:** stesse 384 dimensioni e stesso pooling (media), quindi nessun cambio al database.
   - **Pagina MEMORIA:** lo suggerisce e lo spiega. Dopo il cambio, «Ricalcola i vettori» rifà gli embedding di ricordi e documenti.
   - **Valore predefinito:** resta all-MiniLM-L6-v2, perché cambiarlo da solo lascerebbe i vettori già salvati senza confronto finché non si ricalcolano.
   - **Controllo in CI:** `scripts/check_embedding_pin.py` controlla in CI il commit e le impronte. Se non corrispondono stampa quelli da scrivere, così un modello nuovo si fissa senza scaricarlo a mano.
3. **La conversazione** (`app/memory/store.py`):
   - **Turni recenti:** ogni run riceve nel livello L5 gli ultimi 3 turni della stessa sessione, prima dei ricordi trovati per somiglianza.
   - **Riassunto:**
     - quando una sessione supera 30 run, le 15 più vecchie diventano un unico ricordo «Summary of 15 earlier exchanges», con una riga «- domanda -> risposta» per run, accorciate;
     - i loro episodi si cancellano;
     - il riassunto si costruisce dal testo, senza chiamare il modello: niente costo né attesa, ed è ripetibile.
   - **Ricordi non affidabili:** se anche una sola run del gruppo aveva contenuto esterno, il riassunto è non affidabile e il Context Manager lo mette tra i dati.

## Consequences
- **«E domani?» dopo «che tempo fa a Milano?»:** il primo turno è nel contesto anche senza parole in comune.
- **Conversazioni lunghe:** la memoria non cresce di un episodio per comando all'infinito, e il recupero trova meno doppioni.
- **Dettagli persi:** le risposte vecchie riassunte perdono i dettagli oltre i 200 caratteri.
- **Test:**
  - `tests/agent_engine/test_documents.py`: cartelle degli agenti, doppioni, rimozione, senza cartella di lavoro;
  - `tests/agent_engine/test_context_rag.py`: turni recenti nella stessa sessione e non in un'altra, riassunto, affidabilità;
  - `frontend/tests/memory.test.tsx`: le cartelle in DOCUMENTI.
- **Non verificato qui:**
  - la qualità del modello multilingue sull'italiano, perché huggingface.co non è raggiungibile da questa sessione (le impronte vengono dalla CI);
  - le cartelle vere del PC dell'utente.

## Alternatives considered
- **Riassunto scritto dal modello:** più leggibile, ma su CPU costa minuti e con un modello a pagamento costa soldi a ogni soglia. Scartato per ora.
- **Modello multilingue fp32:** leggermente più preciso, ma quattro volte più pesante in RAM. Scartato.
- **Il multilingue come predefinito:** meglio per l'italiano, ma rompe in silenzio la ricerca per significato di chi ha già dei ricordi. Rimandato: si sceglie in MEMORIA.
