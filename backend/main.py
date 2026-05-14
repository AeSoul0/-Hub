from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize the FastAPI application with the custom project name
app = FastAPI(
    title="ÆHub API", 
    description="Backend for the ÆHub (Ethereum Hub) Personal Dashboard"
)

# CORS (Cross-Origin Resource Sharing) Configuration
# This middleware allows the frontend (e.g., Next.js running on port 3000) 
# to communicate with this backend securely without being blocked by the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:2003",], # Default port for Next.js frontend
    allow_credentials=True,
    allow_methods=["*"], # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"], # Allow all request headers
)

# Root endpoint to check if the server is up and running
@app.get("/")
def read_root():
    return {
        "status": "Online",
        "message": "ÆHub API is ready to serve!",
        "version": "0.1.0"
    }

# Mock endpoint for testing data fetching from the frontend
@app.get("/api/weather")
def get_weather():
    # This is a mockup response. 
    # We will connect this to a real API (like OpenWeatherMap) later.
    return {
        "city": "Rome", 
        "temperature": "22°C", 
        "condition": "Sunny"
    }