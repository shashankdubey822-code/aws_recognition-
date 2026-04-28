import os
import asyncio
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uvicorn

# Custom Modules
from core.config import LOG_FILE
from core.state import attendance_memory
from api.websocket import websocket_endpoint
from services.aws_client import ensure_collection_exists

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    
    # 1. Initialize AWS Rekognition Collection
    try:
        ensure_collection_exists()
    except Exception as e:
        # 🔧 FIX #3: DON'T SWALLOW ERRORS! Log them!
        print(f"❌ CRITICAL ERROR during AWS init: {e}")
        print(f"   Check your AWS credentials in .env file")
        # Still let app start but with warning
        print(f"   App starting in degraded mode (face detection DISABLED)")

    # 2. Load historical logs into RAM
    try:
        if os.path.exists(LOG_FILE):
            df = pd.read_csv(LOG_FILE)
            for _, row in df.iterrows():
                attendance_memory.insert(0, {"name": row['Name'], "time": row['Time']})
            print(f"✅ Loaded {len(attendance_memory)} records.")
        else:
            with open(LOG_FILE, "w") as f: f.write("Name,Time\n")
            print(f"✅ Created new attendance log: {LOG_FILE}")
    except Exception as e:
        print(f"⚠️ WARNING: Could not load attendance logs: {e}")
        print(f"   Starting with empty attendance memory")
    
    yield
    # --- SHUTDOWN PHASE ---
    print("🛑 Shutting down...")
    pass

# --- FastAPI Application ---
app = FastAPI(title="AWS Rekognition Attendance AI", version="3.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register the websocket route
app.add_api_websocket_route("/ws", websocket_endpoint)

from fastapi.responses import HTMLResponse, FileResponse

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main application dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/logs")
async def download_logs():
    """Download the attendance CSV file."""
    if os.path.exists(LOG_FILE):
        return FileResponse(LOG_FILE, media_type='text/csv', filename="attendance_log.csv")
    return {"error": "Attendance log not found yet. Mark some attendance first!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)