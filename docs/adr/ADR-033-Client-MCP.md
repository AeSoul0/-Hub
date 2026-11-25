# ADR-033: Client MCP

## Status
**Accepted** (2026-11-25, dopo Q1; decisione dell'utente dello stesso giorno: rischio alto con approvazione per ogni tool MCP, token nel keyring)

## Context
- **Il ponte MCP era uno stub.** `mcp_bridge.py` controllava l'indirizzo contro `AEHUB_MCP_ALLOWED_SERVERS` (ADR-026), ma non si collegava a nessun server e non esponeva nessun tool.
- **Il pacchetto `mcp` 2.3 era già tra le dipendenze.** Ha un client per Streamable HTTP (`mcp.Client`, `streamable_http_client`) e il server `MCPServer`, che serve anche nei test.
- **Cosa fa un tool di un server non si può sapere.** Il server dichiara una descrizione e degli `annotations` (per esempio `readOnlyHint` o `destructiveHint`), ma sono testo di terzi: un server può dichiarare "sola lettura" per un tool che cancella.
- **Alcuni server chiedono un login** (per esempio Notion o un calendario). Le chiavi in ÆHub non stanno mai in un file o nel database: il launcher le tiene nel keyring del sistema e le passa al backend nell'ambiente.

## Decision
1. **Un client vero, solo Streamable HTTP.**
   - Il client si collega solo agli indirizzi in `AEHUB_MCP_ALLOWED_SERVERS`.
   - Gli indirizzi devono usare https, oppure http solo verso questo computer (`localhost`, `127.0.0.1`, `::1`). Un token non attraversa mai la rete in chiaro.
   - **Niente server stdio:** vorrebbe dire lanciare un comando locale, che è un altro confine.
   - I redirect valgono solo dentro la stessa origine, come fa già l'SDK.
2. **Ogni server: `list_tools()`.** Il client chiede i tool:
   - all'avvio, in background, così un server lento non blocca l'API;
   - quando cambia l'elenco dei server;
   - dal pulsante **Ricollega** di STRUMENTI (`POST /api/tools/mcp/refresh`, solo il proprietario).

   Un server che non risponde mostra il suo errore e non ha tool; gli altri non cambiano.
3. **Una sola skill, `mcp`.** Ogni tool diventa `mcp_<server>_<tool>`, al massimo 64 caratteri, sicuro per ogni provider. Il nome del server viene dall'host: `https://mcp.notion.com/mcp` → `notion`, `http://127.0.0.1:9000/mcp` → `local9000`. Un nome già preso fa saltare il tool, con un avviso nel log.
4. **Il rischio lo decide il proprietario, non il server.**
   - Ogni tool MCP parte a rischio **alto** e chiede l'approvazione **a ogni chiamata** (`requires_approval`).
   - Il proprietario lo abbassa tool per tool da STRUMENTI: `AEHUB_MCP_TOOL_RISK`, `tool=low|medium`. Riportarlo ad alto toglie la voce.
   - Gli `annotations` del server non contano.
   - Basso o no, l'output di un tool MCP resta **non affidabile**. Arriva al modello dentro il recinto `<untrusted_tool_output>`, e dopo ogni azione a rischio alto aspetta un umano (PolicyEngine).
   - Un cambio di rischio vale dalla run dopo, senza ricollegarsi.
5. **Login: un token per host, nel keyring.**
   - Il segreto `AEHUB_MCP_TOKENS` vale `host=token,host=token`, con l'host e la sua porta, se c'è.
   - Il launcher (`scripts/aehub.py setup`) lo salva nel keyring e lo passa al backend.
   - Il client lo manda come `Authorization: Bearer` **solo** al suo host.
   - **OAuth non c'è:** i server che vogliono solo OAuth restano fuori finché non serve davvero.
6. **Ogni chiamata apre la sua connessione e la chiude.**
   - Nessuna sessione resta aperta tra una run e l'altra.
   - Limiti: 15 secondi per collegarsi e leggere l'elenco, 60 secondi per una chiamata, 8000 caratteri di risultato.
   - I risultati diventano testo:
     - le immagini e le risorse binarie sono nominate, non passate;
     - `isError` diventa una chiamata fallita, registrata come tale dal Tool Gateway.
7. **Tutto passa dal Tool Gateway,** come ogni altro tool: policy, tool spenti, schema dell'input dichiarato dal server, approvazione, audit, budget.

## Consequences
- I tool MCP compaiono nel catalogo di STRUMENTI, nella scheda **Server MCP**, con un menu del rischio per ciascuno. La sezione Confini mostra lo stato di ogni server: collegato e con quanti tool, oppure l'errore. Dice anche se c'è un token nel keyring.
- Un server nuovo non può fare niente senza un clic del proprietario: o approva la singola chiamata, o abbassa il rischio di quel tool.
- L'indice delle skill vede la descrizione e il nome dei tool MCP: un compito che li nomina li sceglie, gli altri no.
- I test (`tests/agent_engine/test_mcp_client.py`) avviano un vero `MCPServer` su `127.0.0.1` e verificano:
  - elenco dei tool, chiamata ed errore;
  - rischio abbassato;
  - token mandato solo al suo host;
  - server muto;
  - http verso fuori rifiutato;
  - con il motore vero, la run che si ferma sull'approvazione senza chiamare il server.

## Alternatives considered
- **Fidarsi degli `annotations` del server** per il rischio: è testo di terzi, quindi no.
- **Una skill per server:** il registro non toglie skill a caldo. Una skill sola si aggiorna con `refresh_skill`, come le skill importate.
- **OAuth subito:** più codice e un flusso nel browser. Il token copre i server che lo accettano; OAuth si aggiunge quando un server lo richiede.
- **Server stdio:** sono comodi, ma aprono l'esecuzione di comandi locali, e richiederebbero un confine a parte.
