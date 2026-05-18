import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import media, academic 

# --- WINDOWS ASYNCIO EVENT LOOP FIX FOR PLAYWRIGHT ---
# On Windows, FastAPI/Uvicorn defaults to SelectorEventLoop which does not
# support asynchronous subprocess management (required by Playwright to spawn browsers).
# Forcing WindowsProactorEventLoopPolicy resolves the NotImplementedError.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# -----------------------------------------------------

app = FastAPI(title="AeSouls Hub API Server")

# --- CROSS-ORIGIN RESOURCE SHARING (CORS) CONFIGURATION ---
# This middleware allows your local Next.js frontend (typically running on port 3000)
# to communicate with this backend instance running on port 3002.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to specific origins (e.g., ["http://localhost:3000"])
    allow_credentials=True,
    allow_methods=["*"], # Allow all standard HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"], # Allow all custom and standard request headers
    expose_headers=["Content-Disposition"] # Essential for the frontend to read binary payload file names (e.g., Media_Sync MP3 titles)
)

# --- ROUTER MOUNTING ---
# Registers the separate API endpoints grouped under modular routers
app.include_router(media.router)
app.include_router(academic.router)

@app.get("/")
def read_root():
    """
    Heartbeat endpoint to quickly verify backend status 
    and provide visual feedback to the dashboard's system status indicator.
    """
    return {"status": "Online"}

if __name__ == "__main__":
    import uvicorn
    # Start the local development server executing on host loopback with live reload tracking
    uvicorn.run("main:app", host="127.0.0.1", port=3002, reload=True)