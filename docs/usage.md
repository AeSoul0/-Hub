# Usare ÆHub dall'API

Le richieste all'agente per chi scrive codice: testo, documenti, client Python, voce, casa, strumenti e comandi. Per l'uso di tutti i giorni dal Nucleo c'è la [guida](guida.md).

## Usage

### Text agent request

The current orchestration API exposes:

```text
POST /api/orchestrator/ask
```

The endpoint expects multipart form data.

Example:

Every `/api/` route (except `/api/auth/`) needs the HttpOnly session cookie that `/api/auth/login` sets; it is the only credential (no `Authorization` header, no `X-Session-ID`).

```bash
curl -c cookies.txt -X POST "http://localhost:3002/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"key": "replace_with_your_AEHUB_SECRET_KEY"}'

curl -b cookies.txt -X POST "http://localhost:3002/api/orchestrator/ask" \
  -F "text=Search the web for the latest news about pgvector and summarize it."
```

The reply comes back in the response, and the run shows live in the Nucleo and on the Runs page. The agent may use the web-search tool (DuckDuckGo); its results are untrusted content.

### Asking about your documents

Put text, Markdown or PDF files in the working folder (`./workspace`, or the folder chosen with `setup`) and ask about them:

```text
When should I water the tomatoes? Check my notes.
```

The agent calls `search_documents`, which brings the index up to date (only new or changed files are read, deleted ones leave the index) and returns the best excerpts. Every fact in the answer carries its source: `[doc: notes/garden.md#L3-9]` for lines of a text file, `[doc: report.pdf#p3]` for a PDF page.

* Hidden files and folders are skipped, and so is any link that leads outside the working folder.
* Documents are treated as untrusted data: after a search, any HIGH-risk action needs your approval, even if a document tells the agent otherwise. The same holds in a later session that recalls that conversation.
* Document excerpts are never stored as preferences or rules, and they are not recalled automatically: only `search_documents` reads them.
* `GET /api/documents` lists the indexed files (with errors such as an encrypted PDF); `POST /api/documents/sync` re-indexes now, which is useful after copying many files at once. Both need file access (the admin role).

### Python client example

```python
import httpx

API_URL = "http://localhost:3002"
SECRET_KEY = "replace_with_your_AEHUB_SECRET_KEY"

with httpx.Client(base_url=API_URL, timeout=120) as client:
    # The login sets the session cookie; the client sends it from now on.
    client.post("/api/auth/login", json={"key": SECRET_KEY}).raise_for_status()

    response = client.post(
        "/api/orchestrator/ask",
        data={"text": "Search the web for the latest news about pgvector."},
    )

response.raise_for_status()
print(response.json())
```

### Voice

Voice runs on this machine: faster-whisper turns speech into text and Piper speaks the reply, both on the CPU. No audio leaves the computer, and voice works offline once the models are downloaded (about 150 MB and 60 MB, on first use).

- The microphone button of the Nucleo (or the space bar) records and sends the audio to `/api/orchestrator/listen`; the WebSocket accepts the same audio. The sphere follows the real level of your voice and of the reply.
- The transcript is your instruction, checked like a typed one.
- **A HIGH-risk action asked by voice always waits for your approval on screen**, also in a clean run: the microphone also hears a TV or another person.
- `AEHUB_VOICE=off` turns voice off. Without the speech engine the written reply still arrives.
- **The VOCE page** of the Control Plane (F3, ADR-024) changes the recognition model and language, the voice and its engine without a restart, plays a preview and lists the models already downloaded with their size.
- **ElevenLabs (optional, off by default).** Choose it on the VOCE page and add `ELEVENLABS_API_KEY` (the desktop app saves it in the OS keyring; with Docker use `python scripts/aehub.py setup`). The text of the replies then goes to ElevenLabs; your voice never does. Piper speaks whenever ElevenLabs cannot: no key or voice, an error, or a reply over 2,500 characters.
- **SpaceXAI (optional, off by default, ADR-038).** Choose it on the VOCE page, with the voice `eve` (energetic and cheerful, British accent) or `altair` (formal, elegant) and the language it reads in (`it`, `en`, `fr`, always explicit). Add `XAI_API_KEY` the same way as the ElevenLabs key. Pay per use: 15 $ per million characters, about 2.25 $ a month for 10 replies of 500 characters a day. Piper speaks whenever SpaceXAI cannot.
- A run asked by voice answers by voice also when it resumes after an approval.

### Home devices

The agent controls lights and locks through an MQTT broker on your network (Mosquitto, Zigbee2MQTT, Tasmota).

**From the CASA page** (no restart):

1. Set the broker address and, when it needs one, the user. The password goes in the keyring: the desktop app saves it from the page, otherwise use `python scripts/aehub.py setup` and restart. **Prova il collegamento** tests the connection.
2. Add your devices: name, type (`light` or `lock`), MQTT topic and format (`zigbee2mqtt`, the default, or `tasmota` for lights). The home tools appear on their own.

**From a file**, if you prefer:

1. Copy `config/home.example.json` to `config/home.json` and list your devices.
2. In `backend/.env` set `AEHUB_HOME_DEVICES=/app/config/home.json` and `AEHUB_MQTT_URL`, plus `AEHUB_MQTT_USERNAME` when the broker needs a user. In the desktop app, `home.json` goes next to the database in `%LOCALAPPDATA%\AEHub`.
3. Restart. The configuration check reports an invalid file or a missing broker.

Both lists work together and CASA shows the file's devices read only. An id may appear in only one of them.

Each action is its own tool with its own risk: listing devices, a light, and locking a door are LOW; **unlocking a door is HIGH**. From a run it always waits for approval. From CASA it needs a second click, recorded as the approval of that call. Commands sent from the page go through the same Tool Gateway as the agent's, so a tool turned off in STRUMENTI stays off.

The agent names a device you declared, never a topic or a host. The device file must stay outside the agent's working folder: there the agent's file tools could change it. Devices declared on the page live in the database, out of reach of those tools.

CASA shows the last command sent and says plainly that it is not proof the device obeyed. **Leggi lo stato** asks the device: Zigbee2MQTT topics ending in `/set` and Tasmota `cmnd/<name>/POWER` topics are supported.

### Which tools a run sees

At the start of every run the skill index, a SQLite database of its own, picks from your task alone the tools it names (at most `AEHUB_TOOL_TOP_K`). The model is shown only those, and a call to any other tool is refused, so an instruction hidden in a web page or a document cannot reach a tool your task never asked for. When no word of the task matches a tool, every tool is shown, as before. On the evaluation suite this cut the mean cost per case by about a third.

### Slash commands

`/stop` is the only command (`/clear`, `/precise`, `/creative`, `/deep` and `/fast` never had an effect and were removed in M15). To stop a running agent, use **Stop** on the Runs page.

---
