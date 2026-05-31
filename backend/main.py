import sys
import asyncio
import json
import os
import base64
import tempfile
import httpx
import edge_tts
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from litellm import acompletion, RateLimitError
from dotenv import load_dotenv
from routers import media, academic, orchestrator


load_dotenv()

# Windows fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="AeSouls Hub API Server")

# =====================================================================
# CORS (MOBILE SAFE)
# =====================================================================

"""
CORS CONFIGURATION
------------------
Allows frontend (Next.js) to call backend APIs safely.
Without this, browsers will block requests with:
"TypeError: Failed to fetch"
"""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(media.router)
app.include_router(academic.router)
app.include_router(orchestrator.router)

# =====================================================================
# HISTORY
# =====================================================================
HISTORY_FILE = "chat_history.json"


def save_interaction(user_text: str, ai_text: str, input_type: str):
    record = {
        "timestamp": datetime.now().isoformat(),
        "type": input_type,
        "user_prompt": user_text,
        "aesoul_response": ai_text
    }

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []

    history.append(record)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

# =====================================================================
# AUDIO -> TEXT
# =====================================================================
async def process_audio_to_text(base64_audio: str):
    temp_path = None
    try:
        if "," in base64_audio:
            base64_audio = base64_audio.split(",")[1]

        audio_bytes = base64.b64decode(base64_audio)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp:
            temp.write(audio_bytes)
            temp_path = temp.name

        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(temp_path, "rb") as f:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    files={"file": (os.path.basename(temp_path), f, "audio/webm")},
                    data={"model": "whisper-large-v3"},
                    headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
                )

        if response.status_code == 200:
            return response.json().get("text", "")

        return "Transcription error."

    except Exception as e:
        print(f"STT Error: {e}")
        return "Audio processing failed."

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

# =====================================================================
# TEXT -> AUDIO
# =====================================================================
async def process_text_to_audio(text: str):
    try:
        os.makedirs("audio_cache", exist_ok=True)

        file_path = os.path.join(
            "audio_cache",
            f"response_{int(datetime.now().timestamp())}.mp3"
        )

        communicate = edge_tts.Communicate(text, "it-IT-ElsaNeural")
        await communicate.save(file_path)

        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    except Exception as e:
        print(f"TTS Error: {e}")
        return ""

# =====================================================================
# WEBSOCKET ORCHESTRATOR
# =====================================================================
@app.websocket("/ws/orchestrator")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🟢 Client connected")

    api_key = os.getenv("OPENROUTER_API_KEY")

    async def safe_send(payload: dict):
        try:
            await websocket.send_json(payload)
        except:
            raise WebSocketDisconnect()

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            input_type = payload.get("type", "text_input")
            user_context = payload.get("context", {})

            user_text = (
                await process_audio_to_text(payload.get("data"))
                if input_type == "audio_input"
                else payload.get("data")
            )

            if not user_text:
                continue

            await safe_send({"type": "status", "data": "thinking"})

            system_prompt = (
                "You are AeSoul, the dashboard AI. "
                f"Context: {json.dumps(user_context)}. "
                "Use only provided data. No markdown."
            )

            retries = 3

            while retries > 0:
                try:
                    response = await acompletion(
                        model="openrouter/openai/gpt-oss-120b:free",
                        api_key=api_key,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_text}
                        ],
                        stream=True
                    )

                    full_text = ""

                    async for chunk in response:
                        delta = chunk.choices[0].delta.content or ""
                        full_text += delta

                    await safe_send({
                        "type": "stream_end",
                        "full_text": full_text
                    })

                    audio = await process_text_to_audio(full_text)

                    if audio:
                        await safe_send({
                            "type": "audio_stream",
                            "data": audio
                        })

                    save_interaction(user_text, full_text, input_type)
                    break

                except RateLimitError:
                    retries -= 1
                    await safe_send({
                        "type": "status",
                        "data": "rate_limited_retrying"
                    })
                    await asyncio.sleep(3)

                except Exception as e:
                    print(f"LLM error: {e}")
                    await safe_send({
                        "type": "error",
                        "message": "Generation failed"
                    })
                    break

    except WebSocketDisconnect:
        print("🔴 Client disconnected")

    except Exception as e:
        print(f"❌ Critical error: {e}")

# =====================================================================
# RUN SERVER (MOBILE READY)
# =====================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",   # 🔥 IMPORTANT: mobile access
        port=3002,
        reload=True
    )