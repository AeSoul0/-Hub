import base64
import os
import re

import edge_tts
from dotenv import load_dotenv
import hashlib
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, Request

# ... (rest of imports remain intact, we just add Request and hashlib, wait, imports are at top)
from groq import AsyncGroq
from app.core import database

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


from app.core.event_bus import event_bus

# ==============================================================================
# MAIN PROCESSING CORE
# ==============================================================================

from app.runtime.aurora import get_aurora_app
from langchain_core.messages import HumanMessage

from app.core.security import PromptInjectionFilter

async def generate_ai_response(
    user_intent: str | list, system_prompt: str, ui_context: str, session_id: str
):
    """
    Main cognitive assembly processor.
    Invokes the compiled LangGraph JARVIS Core, passing the user_intent and retrieving the final artifact/state.
    """
    try:
        # Extract string for sanitization if it's a multimodal list
        intent_str = user_intent[0]["text"] if isinstance(user_intent, list) else user_intent
        PromptInjectionFilter.sanitize(intent_str)
    except ValueError as e:
        await event_bus.publish(session_id, "log", f"[Security] {str(e)}")
        await event_bus.publish(session_id, "notification", {"title": "Security Alert", "content": str(e)})
        return
        
    session_config = database.get_settings(session_id)
    
    # Publish diagnostic event for observability
    await event_bus.publish(session_id, "log", f"[System] Routing intent to A.U.R.O.R.A. Core: {intent_str[:30]}...")

    # LangGraph Invocation
    try:
        initial_state = {
            "messages": [HumanMessage(content=user_intent)],
            "session_id": session_id,
            "current_intent": ""
        }
        
        # Invoke graph asynchronously with recursion limit and timeout
        import asyncio
        app_instance = await get_aurora_app()
        final_state = await asyncio.wait_for(
            app_instance.ainvoke(
                initial_state,
                config={
                    "configurable": {"thread_id": session_id},
                    "recursion_limit": 15
                }
            ),
            timeout=45.0
        )
        ai_response_text = final_state["messages"][-1].content
        
        
    except Exception as e:
        ai_response_text = f"Errore del runtime agentico: {str(e)}"
        print(f"Graph Execution Error: {e}")

    clean_response = clean_text_for_speech(ai_response_text)
    base64_audio = await generate_voice_base64(clean_response)

    database.save_chat(session_id, intent_str, clean_response)

    return {"transcription": clean_response, "audio_base64": base64_audio}


# ==============================================================================
# CONTROLLER ENDPOINTS
# ==============================================================================

@router.post("/listen")
async def process_orchestration_voice(
    request: Request,
    file: UploadFile = File(...),
    ui_context: str = Form(default=""),
    # SECURITY: Extract session identifier from HTTP headers to guarantee isolation
    x_session_id: str = Header(default="default-session"),
):
    try:
        # Cryptographic binding of Session to User Identity
        auth_token = request.cookies.get("aehub_auth_token", "unauth")
        secure_session_id = hashlib.sha256(f"{auth_token}:{x_session_id}".encode()).hexdigest()
        
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
            user_intent, AESOUL_SYSTEM_PROMPT, ui_context, secure_session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice node failure: {str(e)}") from e


@router.post("/ask")
async def process_orchestration_text(
    request: Request,
    text: str = Form(...),
    ui_context: str = Form(default=""),
    image: UploadFile = File(default=None),
    # SECURITY: Extract session identifier from HTTP headers to guarantee isolation
    x_session_id: str = Header(default="default-session"),
):
    try:
        # Cryptographic binding of Session to User Identity
        auth_token = request.cookies.get("aehub_auth_token", "unauth")
        secure_session_id = hashlib.sha256(f"{auth_token}:{x_session_id}".encode()).hexdigest()

        if text.strip().startswith("/"):
            return await execute_slash_command(text, secure_session_id)

        # Multimodal Image Handling
        if image:
            image_bytes = await image.read()
            import base64
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Construct a Langchain-compatible multimodal message content array
            content_payload = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:{image.content_type};base64,{img_b64}"}}
            ]
            # Override text with the multimodal payload for generate_ai_response
            text = content_payload

        return await generate_ai_response(text, AESOUL_SYSTEM_PROMPT, ui_context, secure_session_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text node failure: {str(e)}") from e