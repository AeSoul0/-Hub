import base64
import os
import re
import json
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from groq import AsyncGroq
import edge_tts
from dotenv import load_dotenv

# ==============================================================================
# ENVIRONMENT & RUNTIME INITIALIZATION
# ==============================================================================

# Ingest environment runtime variables from the local storage configurations (.env)
load_dotenv()

# Initialize the modular API router under the 'orchestrator' sub-context domain
router = APIRouter(
    prefix="/api/orchestrator",
    tags=["orchestrator"]
)

# Fetch the secure credential token dynamically from runtime environment memory layers
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Failsafe architectural check enforcing valid environment settings before initializing downstream routines
if not GROQ_API_KEY:
    raise RuntimeError("CRITICAL CORE CONFIGURATION FAULT: 'GROQ_API_KEY' missing from environment scope.")

# Instantiate the asynchronous Groq client infrastructure using your parsed token variable
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Global configuration registry managing hyper-parameters dynamically altered by execution commands
SESSION_CONFIG = {
    "temperature": 0.75,
    "max_tokens": 300,
    "deep_mode": False
}

# ==============================================================================
# DATA PROCESSING & SANITIZATION HELPERS
# ==============================================================================

def clean_text_for_speech(text: str) -> str:
    """
    Sanitizes raw model output strings by programmatically removing Markdown syntaxes,
    internal citation hashes, and literal backslashes that disrupt Text-to-Speech audio formatting.
    Transforms raw newline tags to plain full stops to enforce fluid cadence breaks.
    """
    if not text:
        return ""
        
    # Programmatically strip out citation anchors matching patterns
    text = re.sub(r"\\", "", text)
    
    # Remove literal backslashes safely without disrupting Python system string encoding literals
    text = text.replace("\\", "")
    
    # Strip layout-formatting artifacts like markdown asterisks, hashes, underscores, backticks and brackets
    text = text.replace("*", "").replace("#", "").replace("_", "").replace("[", "").replace("]", "").replace("`", "")
    
    # Replace layout line breaks with a standard punctuation marker to construct natural human pacing
    text = text.replace("\n", ". ")
    
    # Flatten redundant adjacent spaces into a single spacing metric
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


async def generate_voice_base64(text: str) -> str:
    """
    Assembles a real-time speech compilation buffer via Edge-TTS streaming mechanics.
    Converts raw, uncompressed text inputs into high-fidelity premium human-grade neural audio
    blocks using volatile system memory directly to eliminate storage I/O latency overhead.
    """
    # Utilizing Microsoft Azure's premium human-grade neural female communication profile
    voice = "it-IT-ElsaNeural" 
    communicate = edge_tts.Communicate(text, voice)
    
    # Aggregate raw media segments directly inside a volatile memory byte sequence array
    tts_audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            tts_audio_data += chunk["data"]

    # Map the compiled raw binary buffer onto an isolated, network-safe standard Base64 string payload
    return base64.b64encode(tts_audio_data).decode("utf-8")


# ==============================================================================
# RECALL MATRIX & HISTORY MANAGEMENT LAYERS
# ==============================================================================

def save_chat_to_history(user_text: str, ai_text: str):
    """
    Logs user instructions and the corresponding processed system replies inside a
    persistent local JSON ledger file. Includes dynamic file generation and error-safe parsing logic.
    """
    history_file = "chat_history.json"
    history_data = []
    
    # Open and map current historical database records if present on the system disk
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except json.JSONDecodeError:
            # Failsafe protection block executing whenever the internal JSON file structure is unreadable
            history_data = []

    # Format the new dialogue interaction object including standard automated ISO timestamps
    interaction = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_text.strip(),
        "atom": ai_text.strip()
    }
    history_data.append(interaction)

    # Persist the updated array back to the system storage cluster
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=4, ensure_ascii=False)


def get_recent_chat_context(limit: int = 5) -> list:
    """
    Extracts the tail-end transactions from the persistent JSON historical ledger file.
    Translates raw log metrics into structured LLM message objects to provide short-term
    conversational context tracking without generating massive token resource drain.
    """
    history_file = "chat_history.json"
    context_messages = []
    
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Fetch only the specified slice limit window to maintain maximum computing speed
                recent_data = data[-limit:]
                for interaction in recent_data:
                    if "user" in interaction and "atom" in interaction:
                        context_messages.append({"role": "user", "content": interaction["user"]})
                        context_messages.append({"role": "assistant", "content": interaction["atom"]})
        except Exception:
            # Silence internal file decoding faults to prevent breaking core pipeline transactions
            pass
            
    return context_messages


# ==============================================================================
# COMMAND PROCESSING LOGIC (CLI ROUTING SYSTEM)
# ==============================================================================

async def execute_slash_command(cmd: str):
    """
    Intercepts terminal-style slash primitives written into the user interaction box.
    Modifies runtime environment hyper-parameters, configurations, and core memory
    ledger indices instantly, rendering vocal configuration reports back to the speaker.
    """
    global SESSION_CONFIG
    cmd = cmd.lower().strip()
    reply_text = ""
    
    if cmd == "/clear":
        # Overwrite the persistent storage layout array with a clean empty database block
        history_file = "chat_history.json"
        if os.path.exists(history_file):
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump([], f)
        reply_text = "System memory initialized. Log sequence cleared."
        
    elif cmd == "/precise":
        SESSION_CONFIG["temperature"] = 0.1
        reply_text = "Precision mode activated. Engaging low-variance logical sequence."
        
    elif cmd == "/creative":
        SESSION_CONFIG["temperature"] = 0.9
        reply_text = "Creative mode engaged. Neural variance increased."
        
    elif cmd == "/deep":
        SESSION_CONFIG["max_tokens"] = 1024
        SESSION_CONFIG["deep_mode"] = True
        reply_text = "Deep reasoning enabled. Synthesis parameters disabled."
        
    elif cmd == "/fast":
        SESSION_CONFIG["max_tokens"] = 300
        SESSION_CONFIG["deep_mode"] = False
        SESSION_CONFIG["temperature"] = 0.75
        reply_text = "Rapid operation engaged. Standard synthesis parameters restored."
        
    else:
        reply_text = "Unknown directive. Accepted commands are clear, precise, creative, deep, or fast."

    # Process immediate voice report synthesis for the executed command telemetry
    base64_audio = await generate_voice_base64(reply_text)
    return {
        "transcription": reply_text,
        "audio_base64": base64_audio
    }


# ==============================================================================
# CONTROLLER ENDPOINTS
# ==============================================================================

@router.post("/listen")
async def process_orchestration_voice(
    file: UploadFile = File(...), 
    system_prompt: str = Form(...),
    ui_context: str = Form(default="") # Dynamic frontend UI state injection parameter
):
    """
    Ingests binary client voice recordings. Transcribes analog data waves into plain
    text strings through Groq's hardware-accelerated Whisper-Large-V3 infrastructure.
    """
    try:
        audio_bytes = await file.read()
        
        temp_file = "temp_input.webm"
        with open(temp_file, "wb") as f:
            f.write(audio_bytes)
            
        with open(temp_file, "rb") as f:
            transcript = await groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=(temp_file, f.read()),
                response_format="text"
            )
        user_intent = transcript
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return await generate_ai_response(user_intent, system_prompt, ui_context)
        
    except Exception as e:
        print(f"\n[!] CRITICAL ORCHESTRATOR FAULT (VOICE): {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Voice execution node failure: {str(e)}")


@router.post("/ask")
async def process_orchestration_text(
    text: str = Form(...), 
    system_prompt: str = Form(...),
    ui_context: str = Form(default="") # Dynamic frontend UI state injection parameter
):
    """
    Intercepts incoming manual keyboard operations entered through the terminal bar.
    Evaluates requests against CLI slash paths and routes outputs through Base64 vocal buffers.
    """
    try:
        if text.strip().startswith("/"):
            return await execute_slash_command(text)
            
        return await generate_ai_response(text, system_prompt, ui_context)
        
    except Exception as e:
        print(f"\n[!] CRITICAL ORCHESTRATOR FAULT (TEXT): {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"Text execution node failure: {str(e)}")


# ==============================================================================
# MAIN PROCESSING CORE
# ==============================================================================

async def generate_ai_response(user_intent: str, system_prompt: str, ui_context: str):
    """
    Main cognitive assembly processor. Bundles architectural instructions, UI card states, 
    historical dialogue memories, and the user's latest command payload into a cohesive runtime matrix.
    """
    # Stage 1: Seed the core execution message array using the initial system prompt constraints
    messages = [{"role": "system", "content": system_prompt}]
    
    # Stage 2: Inject dynamic UI state telemetry if the React frontend broadcasts active widget data
    if ui_context and ui_context.strip():
        context_payload = (
            f"LIVE SYSTEM DASHBOARD CONTEXT:\n"
            f"You have access to the following real-time data from the AeHub interface cards:\n"
            f"{ui_context}\n"
            f"Use this data organically only if the user's query relates to it."
        )
        messages.append({"role": "system", "content": context_payload})

    # Stage 3: Inject systemic instruction overrides whenever Deep Reasoning configuration profiles are active
    if SESSION_CONFIG["deep_mode"]:
        messages.append({
            "role": "system", 
            "content": "OVERRIDE: You are in DEEP REASONING mode. Ignore all previous brevity constraints. Provide a highly detailed, step-by-step analysis."
        })
        
    # Stage 4: Ingest conversational context strings from the data history layer to enable dialogue recall
    historical_context = get_recent_chat_context(limit=5)
    messages.extend(historical_context)
    
    # Stage 5: Append the current interaction directive thread to the top of the context stack
    messages.append({"role": "user", "content": user_intent})
    
    # Stage 6: Trigger inference matrix loop on the remote high-parameter gpt-oss-120b model node
    completion = await groq_client.chat.completions.create(
        model="openai/gpt-oss-120b", 
        messages=messages,
        temperature=SESSION_CONFIG["temperature"],
        top_p=1,
        max_completion_tokens=SESSION_CONFIG["max_tokens"], 
        stream=False 
    )
    raw_response = completion.choices[0].message.content

    # Stage 7: Clean textual results to strip parsing flags before feeding audio synthesis generators
    clean_response = clean_text_for_speech(raw_response)
    
    # Stage 8: Transition sanitized textual structures into standard media voice wave configurations
    base64_audio = await generate_voice_base64(clean_response)

    # Stage 9: Update the network database logs to preserve current transactions for subsequent queries
    save_chat_to_history(user_intent, clean_response)

    # Dispatch final formatted signals directly back to the terminal layout view
    return {
        "transcription": clean_response, 
        "audio_base64": base64_audio
    }