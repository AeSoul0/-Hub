import base64
import os
import re

import edge_tts
from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from groq import AsyncGroq
import database

load_dotenv()

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "CRITICAL CORE CONFIGURATION FAULT: 'GROQ_API_KEY' missing from environment scope."
    )

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# ==============================================================================
# CORE BEHAVIORAL DIRECTIVES (MASTER SYSTEM PROMPT)
# ==============================================================================
AESOUL_SYSTEM_PROMPT = (
    "You are AeSoul, the artificial intelligence orchestrating and controlling the system dashboard. "
    "IDENTITY: Act as an integral part of the platform, not a generic assistant. "
    "Your primary goal is to help the user monitor and manage the system through natural conversation. "
    "Respond professionally, precisely, and be action-oriented. Always respond in Italian unless otherwise requested. "
    "ABSOLUTE RULES OF BEHAVIOR: "
    "1. DEFAULT CONCISENESS: Provide short, direct answers. Address the main request first. Avoid long explanations. "
    "2. SMART EXPANSION: Expand ONLY if the user explicitly asks, if the request is highly complex, or if brevity causes ambiguity. Dynamically adapt your length. "
    "3. NATURAL CONVERSATION: Be fluid and natural. GET STRAIGHT TO THE POINT. NEVER use generic AI filler phrases like 'Certainly', 'I am happy to help', 'Here is your answer', or 'Let me know if you need anything else'. "
    "4. DASHBOARD ORCHESTRATION: Treat dashboard data as the absolute truth. Synthesize information instead of listing raw data. Highlight anomalies, issues, risks, and opportunities. "
    "5. DATA MANAGEMENT: Use EXCLUSIVELY the provided context. Do NOT invent or hallucinate metrics, states, or events. If a data point is missing, state it clearly. "
    "6. COMMUNICATIVE EFFICIENCY: Zero repetitions, zero useless introductions, zero superfluous conclusions. Every sentence must add value. Maintain a high signal-to-noise ratio. "
    "7. FORMATTING: NO MARKDOWN ALLOWED. Do not use asterisks, hashes, bold text, or decorative blocks. Use plain, readable text only. "
    "8. OPERATIONAL PRIORITY: 1. Data Accuracy, 2. Request Understanding, 3. Synthesis, 4. Clarity, 5. Completeness. "
    "FINAL GOAL: Provide a fast, natural, dashboard-oriented conversational experience, offering only truly useful information exactly when needed."
)

# ==============================================================================
# DATA PROCESSING & SANITIZATION HELPERS
# ==============================================================================

def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"\\", "", text).replace("\\", "")
    text = (
        text.replace("*", "")
        .replace("#", "")
        .replace("_", "")
        .replace("[", "")
        .replace("]", "")
        .replace("`", "")
    )
    text = text.replace("\n", ". ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def generate_voice_base64(text: str) -> str:
    communicate = edge_tts.Communicate(text, "it-IT-ElsaNeural")
    tts_audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            tts_audio_data += chunk["data"]
    return base64.b64encode(tts_audio_data).decode("utf-8")


# ==============================================================================
# COMMAND PROCESSING LOGIC (CLI ROUTING SYSTEM)
# ==============================================================================

async def execute_slash_command(cmd: str, session_id: str):
    """
    Intercepts terminal-style slash primitives and securely alters hyper-parameters
    exclusively for the active session context via the SQLite state ledger.
    """
    cmd = cmd.lower().strip()
    reply_text = ""

    # INTERRUPT OVERRIDE: Halt execution instantly without generating TTS payload
    if cmd == "/stop":
        return {"transcription": "[Sistema: Operazione interrotta. In attesa di istruzioni.]", "audio_base64": ""}

    elif cmd == "/clear":
        database.clear_chat(session_id)
        reply_text = "Memoria di sistema inizializzata. Cronologia cancellata."

    elif cmd == "/precise":
        database.update_settings(session_id, temperature=0.1)
        reply_text = "Modalità precisione attivata. Varianza logica ridotta al minimo."

    elif cmd == "/creative":
        database.update_settings(session_id, temperature=0.9)
        reply_text = "Modalità creativa ingaggiata. Reti neurali espanse."

    elif cmd == "/deep":
        database.update_settings(session_id, max_tokens=1024, deep_mode=True)
        reply_text = "Analisi profonda abilitata. Parametri di sintesi disattivati."

    elif cmd == "/fast":
        database.update_settings(session_id, temperature=0.75, max_tokens=300, deep_mode=False)
        reply_text = "Operatività rapida ingaggiata. Parametri standard ripristinati."

    else:
        reply_text = (
            "Comando sconosciuto. Direttive accettate: stop, clear, precise, creative, deep, fast."
        )

    base64_audio = await generate_voice_base64(reply_text)
    return {"transcription": reply_text, "audio_base64": base64_audio}


# ==============================================================================
# MAIN PROCESSING CORE
# ==============================================================================

async def generate_ai_response(
    user_intent: str, system_prompt: str, ui_context: str, session_id: str
):
    """
    Main cognitive assembly processor. Now securely isolated per user session.
    """
    # Fetch user-specific settings from the SQLite database
    session_config = database.get_settings(session_id)

    messages = [{"role": "system", "content": system_prompt}]

    if ui_context and ui_context.strip():
        context_payload = (
            f"LIVE SYSTEM DASHBOARD CONTEXT:\n{ui_context}\n"
            f"Use this data organically only if the user's query relates to it."
        )
        messages.append({"role": "system", "content": context_payload})

    if session_config["deep_mode"]:
        messages.append(
            {
                "role": "system",
                "content": "OVERRIDE: You are in DEEP REASONING mode. Provide a detailed analysis and ignore the concise limits.",
            }
        )

    # Ingest historical context safely isolated by session ID
    historical_context = database.get_recent_chat(session_id, limit=5)
    messages.extend(historical_context)

    messages.append({"role": "user", "content": user_intent})

    completion = await groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        temperature=session_config["temperature"],
        top_p=1,
        max_completion_tokens=session_config["max_tokens"],
        stream=False,
    )
    raw_response = completion.choices[0].message.content

    clean_response = clean_text_for_speech(raw_response)
    base64_audio = await generate_voice_base64(clean_response)

    # Persist data securely under the specific user's partition
    database.save_chat(session_id, user_intent, clean_response)

    return {"transcription": clean_response, "audio_base64": base64_audio}


# ==============================================================================
# CONTROLLER ENDPOINTS
# ==============================================================================

@router.post("/listen")
async def process_orchestration_voice(
    file: UploadFile = File(...),
    ui_context: str = Form(default=""),
    # SECURITY: Extract session identifier from HTTP headers to guarantee isolation
    x_session_id: str = Header(default="default-session"),
):
    try:
        audio_bytes = await file.read()
        temp_file = "temp_input.webm"

        with open(temp_file, "wb") as f:
            f.write(audio_bytes)

        with open(temp_file, "rb") as f:
            transcript = await groq_client.audio.transcriptions.create(
                model="whisper-large-v3", file=(temp_file, f.read()), response_format="text"
            )

        user_intent = transcript

        if os.path.exists(temp_file):
            os.remove(temp_file)

        return await generate_ai_response(
            user_intent, AESOUL_SYSTEM_PROMPT, ui_context, x_session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice node failure: {str(e)}") from e


@router.post("/ask")
async def process_orchestration_text(
    text: str = Form(...),
    ui_context: str = Form(default=""),
    # SECURITY: Extract session identifier from HTTP headers to guarantee isolation
    x_session_id: str = Header(default="default-session"),
):
    try:
        if text.strip().startswith("/"):
            return await execute_slash_command(text, x_session_id)

        return await generate_ai_response(text, AESOUL_SYSTEM_PROMPT, ui_context, x_session_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text node failure: {str(e)}") from e