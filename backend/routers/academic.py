import os
import re
import asyncio
import traceback

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from playwright.async_api import async_playwright
from pydantic import BaseModel

import database
from event_bus import event_bus

router = APIRouter(prefix="/api/academic", tags=["academic"])

os.makedirs("workspace/playwright_sessions", exist_ok=True)

class AcademicLoginRequest(BaseModel):
    cookie_string: str = "" # We make this optional or ignore it in favor of interactive login

# ==============================================================================
# SECURE STATUS EXTRACTION
# ==============================================================================
@router.get("/status")
def get_academic_status(x_session_id: str = Header(default="default-session")):
    data = database.get_academic_data(x_session_id)
    if data:
        return {"status": "success", "data": data}
    return {"status": "unauthenticated"}


@router.post("/logout")
def logout_academic(x_session_id: str = Header(default="default-session")):
    try:
        database.clear_academic_data(x_session_id)
        state_path = f"workspace/playwright_sessions/{x_session_id}_state.json"
        if os.path.exists(state_path):
            os.remove(state_path)
        return {"status": "unauthenticated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to clear session cache") from e


# ==============================================================================
# ASYNC PLAYWRIGHT WORKERS
# ==============================================================================
async def perform_academic_sync(session_id: str):
    """
    Headless sync using storage_state. If auth fails, emits AUTH_REQUIRED.
    """
    state_path = f"workspace/playwright_sessions/{session_id}_state.json"
    
    await event_bus.publish(session_id, "log", "Avvio routine Infostud...")
    
    try:
        async with async_playwright() as p:
            # Check if we have a saved state
            if not os.path.exists(state_path):
                await event_bus.publish(session_id, "AUTH_REQUIRED", "Credenziali non trovate o scadute.")
                return

            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=state_path)
            page = await context.new_page()

            await event_bus.publish(session_id, "log", "Navigazione Infostud (Headless)...")
            await page.goto("https://studenti.uniroma1.it/phoenix/#/grafico", timeout=60000)
            
            # Wait a bit to see if we get redirected to login or stay on the dashboard
            await page.wait_for_timeout(3000)
            
            current_url = page.url
            if "login" in current_url.lower() or "idp" in current_url.lower():
                await event_bus.publish(session_id, "log", "Sessione scaduta. Richiesta autenticazione.")
                await event_bus.publish(session_id, "AUTH_REQUIRED", "Sessione Infostud scaduta.")
                await browser.close()
                return

            await event_bus.publish(session_id, "log", "Cookie validi, estrazione in corso...")
            
            await page.wait_for_timeout(2000) # Give extra time for JSON rendering

            academic_data = {"gpa": 0.0, "exams": 0, "cfu": 0}

            try:
                page_text = await page.locator("body").inner_text()

                gpa_match = re.search(r"(?:media|ponderata|voti)[^\d\n]*(\d{2}[.,]\d{1,2}|\d{2})", page_text, re.IGNORECASE)
                if gpa_match:
                    academic_data["gpa"] = float(gpa_match.group(1).replace(",", "."))

                cfu_match = re.search(r"(?:cfu|crediti)[^\d\n]*(\d+)", page_text, re.IGNORECASE)
                if cfu_match:
                    academic_data["cfu"] = int(cfu_match.group(1))

                exams_match = re.search(r"(?:esami|superati|registrati)[^\d\n]*(\d+)", page_text, re.IGNORECASE)
                if exams_match:
                    academic_data["exams"] = int(exams_match.group(1))

            except Exception as e:
                await event_bus.publish(session_id, "log", f"Scraping problem: {e}")

            database.save_academic_data(session_id, academic_data["gpa"], academic_data["cfu"], academic_data["exams"])
            await event_bus.publish(session_id, "result", academic_data)
            await event_bus.publish(session_id, "log", "[OK] Estrazione completata.")

            await browser.close()

    except Exception as e:
        await event_bus.publish(session_id, "error", f"Automazione fallita: {str(e)}")
        traceback.print_exc()


async def perform_interactive_login(session_id: str):
    """
    Interactive Auth-Recovery (headless=False)
    """
    state_path = f"workspace/playwright_sessions/{session_id}_state.json"
    
    await event_bus.publish(session_id, "log", "Apertura finestra browser per Login manuale...")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto("https://studenti.uniroma1.it/phoenix/")
            
            await event_bus.publish(session_id, "log", "In attesa del completamento del login (SPID/CIE)...")
            
            # Wait until user reaches the dashboard
            await page.wait_for_url("**/phoenix/#/grafico**", timeout=300000) # 5 minutes timeout for 2FA
            
            await event_bus.publish(session_id, "log", "Login rilevato! Salvataggio sessione...")
            
            # Save storage state
            await context.storage_state(path=state_path)
            
            await browser.close()
            
            await event_bus.publish(session_id, "log", "Sessione salvata. Avvio estrazione automatica...")
            
            # Chain the extraction
            await perform_academic_sync(session_id)

    except Exception as e:
        await event_bus.publish(session_id, "error", f"Login interattivo fallito o scaduto: {str(e)}")
        traceback.print_exc()


# ==============================================================================
# ENDPOINTS
# ==============================================================================
@router.post("/sync")
async def start_academic_sync(
    background_tasks: BackgroundTasks, 
    x_session_id: str = Header(default="default-session")
):
    """
    Triggers the headless extraction flow.
    """
    background_tasks.add_task(perform_academic_sync, x_session_id)
    return {"status": "started", "message": "Sincronizzazione in background avviata."}


@router.post("/interactive-login")
async def start_interactive_login(
    background_tasks: BackgroundTasks, 
    x_session_id: str = Header(default="default-session")
):
    """
    Triggers the headed auth-recovery flow.
    """
    background_tasks.add_task(perform_interactive_login, x_session_id)
    return {"status": "started", "message": "Finestra di login in apertura..."}
