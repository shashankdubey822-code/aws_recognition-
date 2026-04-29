import os
import asyncio
import pandas as pd
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uvicorn

# Custom Modules
from core.config import LOG_FILE
from core.state import attendance_memory, PRESENT_IDENTITIES, last_seen, temporal_memory
from api.websocket import websocket_endpoint
from services.aws_client import ensure_collection_exists, delete_all_faces

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    
    # 1. Initialize AWS Rekognition Collection
    try:
        ensure_collection_exists()
    except Exception as e:
        print(f"❌ CRITICAL ERROR during AWS init: {e}")
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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main application dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/logs")
async def download_logs():
    """Download the formatted attendance CSV file."""
    if not os.path.exists(LOG_FILE):
        return {"error": "Attendance log not found yet. Mark some attendance first!"}
    try:
        df = pd.read_csv(LOG_FILE)
        if not df.empty and 'Name' in df.columns:
            # Clean names: john_doe_123 -> John Doe 123
            df['Name'] = df['Name'].apply(lambda x: str(x).replace('_', ' ').title())
            
            # Add Status column
            df['Status'] = 'CLEARANCE GRANTED'
            
        csv_content = df.to_csv(index=False)
        filename = f"Security_Log_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return {"error": f"Failed to generate log: {e}"}

@app.post("/delete_faces")
async def wipe_faces():
    """Trigger Full System Reset: AWS + Local Memory + Local Logs."""
    success, message = delete_all_faces()
    if success:
        attendance_memory.clear()
        PRESENT_IDENTITIES.clear()
        last_seen.clear()
        temporal_memory.clear()
        try:
            with open(LOG_FILE, "w") as f: f.write("Name,Time\n")
        except: pass
        return {"success": True, "message": "Full system reset complete."}
    return {"success": False, "message": message}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
