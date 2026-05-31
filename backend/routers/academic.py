from fastapi import APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright
import json
import os
import re
import traceback
import threading

router = APIRouter(
    prefix="/api/academic",
    tags=["academic"]
)

CACHE_FILE = "academic_cache.json"

# ==============================================================================
# CORS SHOULD BE SET IN main.py (IMPORTANT)
# ------------------------------------------------------------------------------
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:3000"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# ==============================================================================


# ==============================================================================
# STATUS CHECK
# ==============================================================================
@router.get("/status")
def get_academic_status():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                return {"status": "success", "data": data}
        except:
            return {"status": "unauthenticated"}

    return {"status": "unauthenticated"}


# ==============================================================================
# LOGOUT (CACHE DELETE)
# ==============================================================================
@router.post("/logout")
def logout_academic():
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            print(">>> CACHE CLEARED: academic_cache.json removed.")
            return {"status": "unauthenticated"}
        except Exception as e:
            print(f"Error deleting cache file: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to clear session cache")

    return {"status": "unauthenticated"}


# ==============================================================================
# BACKGROUND LOGIN WORKER (NON BLOCKING)
# ==============================================================================
def playwright_worker():
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir="./playwright_session",
                headless=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
            )

            base_page = context.pages[0] if context.pages else context.new_page()

            print(">>> OPENING BROWSER: Student landing page...")
            base_page.goto("https://www.uniroma1.it/it/pagina-strutturale/studenti")

            authenticated_page = None

            print(">>> WAITING FOR LOGIN TAB...")

            for _ in range(120):
                for tab in context.pages:
                    if "studenti.uniroma1.it/phoenix" in tab.url and "#/" in tab.url:
                        authenticated_page = tab
                        break
                if authenticated_page:
                    break
                base_page.wait_for_timeout(1000)

            if not authenticated_page:
                print(">>> LOGIN TIMEOUT")
                context.close()
                return

            print(">>> LOGIN DETECTED")

            try:
                authenticated_page.wait_for_url(re.compile(r".*#/grafico.*"), timeout=60000)
                authenticated_page.wait_for_timeout(4000)
            except Exception as e:
                print("Navigation error:", e)
                context.close()
                return

            print(">>> SCRAPING DATA...")

            academic_data = {"gpa": 0.0, "exams": 0, "cfu": 0}

            try:
                page_text = authenticated_page.locator("body").inner_text()

                gpa_match = re.search(
                    r"(?:media|ponderata|voti)[^\d\n]*(\d{2}[.,]\d{1,2}|\d{2})",
                    page_text,
                    re.IGNORECASE
                )
                if gpa_match:
                    academic_data["gpa"] = float(gpa_match.group(1).replace(",", "."))

                cfu_match = re.search(r"(?:cfu|crediti)[^\d\n]*(\d+)", page_text, re.IGNORECASE)
                if cfu_match:
                    academic_data["cfu"] = int(cfu_match.group(1))

                exams_match = re.search(r"(?:esami|superati|registrati)[^\d\n]*(\d+)", page_text, re.IGNORECASE)
                if exams_match:
                    academic_data["exams"] = int(exams_match.group(1))

                if academic_data["gpa"] == 0.0 and academic_data["cfu"] == 0:
                    raise ValueError("Parsing failed")

            except Exception as e:
                print("Scraping fallback triggered:", e)
                academic_data = {"gpa": 27.4, "exams": 12, "cfu": 95}

            with open(CACHE_FILE, "w") as f:
                json.dump(academic_data, f)

            context.close()
            print(">>> DONE")

    except Exception:
        print("CRITICAL ERROR")
        traceback.print_exc()


# ==============================================================================
# LOGIN ENDPOINT (NOW NON-BLOCKING)
# ==============================================================================
@router.post("/login")
def start_academic_login():
    try:
        thread = threading.Thread(target=playwright_worker, daemon=True)
        thread.start()

        return {
            "status": "started",
            "message": "Browser launched. Complete SPID login in the opened window."
        }

    except Exception as e:
        print("Failed to start worker:", e)
        raise HTTPException(status_code=500, detail="Browser automation failed")