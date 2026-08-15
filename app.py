import os
import asyncio
import pandas as pd
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Custom Modules
from core.config import (
    LOG_FILE, REPORTS_DIR, TEACHER_EMAIL, TEACHER_PASSWORD, 
    SESSION_COOKIE_NAME, DEFAULT_SESSION_DURATION_MIN
)
from core.state import (
    attendance_memory, PRESENT_IDENTITIES, last_seen, 
    temporal_memory, active_session
)
from api.websocket import websocket_endpoint, end_active_session
from services.aws_client import ensure_collection_exists, delete_all_faces
from services.email_service import generate_session_excel

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs("static/intruders", exist_ok=True)
    os.makedirs("static/attendees", exist_ok=True)
    
    # 1. Initialize AWS Rekognition Collection
    try:
        ensure_collection_exists()
    except Exception as e:
        print(f"❌ CRITICAL ERROR during AWS init: {e}")
        print(f"   App starting in degraded mode (face detection DISABLED)")

    # 2. Load historical logs into RAM
    try:
        if os.path.exists(LOG_FILE):
            df = pd.read_csv(LOG_FILE)
            for _, row in df.iterrows():
                roll = row.get('Roll Number', 'N/A') if 'Roll Number' in row else 'N/A'
                name = row.get('Name', 'Unknown')
                time_val = row.get('Time', '')
                attendance_memory.insert(0, {"roll_number": str(roll), "name": str(name), "time": str(time_val)})
            print(f"✅ Loaded {len(attendance_memory)} records into memory.")
        else:
            with open(LOG_FILE, "w", encoding="utf-8") as f: 
                f.write("Roll Number,Name,Time,Date,Status\n")
            print(f"✅ Created new attendance log: {LOG_FILE}")
    except Exception as e:
        print(f"⚠️ WARNING: Could not load attendance logs: {e}")
    
    yield
    # --- SHUTDOWN PHASE ---
    print("🛑 Shutting down server...")
    if active_session.get("active"):
        try:
            await end_active_session("Server Shutdown")
        except Exception:
            pass

# --- FastAPI Application ---
app = FastAPI(title="Nexus AI — Enterprise Attendance & Surveillance", version="3.1.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register the websocket route
app.add_api_websocket_route("/ws", websocket_endpoint)

# --- Authentication Helpers ---
def is_authenticated(request: Request) -> bool:
    """Checks if the user has a valid teacher session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return token == "teacher_authenticated_valid_session"

# --- Authentication Routes ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Renders the teacher login page."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Processes teacher login form credentials."""
    clean_email = email.strip().lower()
    clean_pass = password.strip()

    if clean_email == TEACHER_EMAIL.lower() and clean_pass == TEACHER_PASSWORD:
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value="teacher_authenticated_valid_session",
            max_age=86400, # 1 day
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid Teacher ID or Password. Please try again."}
        )

@app.get("/logout")
async def handle_logout():
    """Logs out teacher and redirects to login."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

# --- Protected Teacher Dashboard ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main teacher monitoring dashboard."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "teacher_email": TEACHER_EMAIL,
        "default_duration": DEFAULT_SESSION_DURATION_MIN
    })

# --- Export Logs & Reports ---
@app.get("/logs")
async def download_logs(request: Request):
    """Download the formatted overall attendance CSV file."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if not os.path.exists(LOG_FILE):
        return {"error": "Attendance log not found yet. Mark some attendance first!"}
    try:
        df = pd.read_csv(LOG_FILE)
        if not df.empty and 'Name' in df.columns:
            df['Name'] = df['Name'].apply(lambda x: str(x).replace('_', ' ').title())
            if 'Status' not in df.columns:
                df['Status'] = 'CLEARANCE GRANTED'
            
        csv_content = df.to_csv(index=False)
        filename = f"Master_Attendance_Log_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return {"error": f"Failed to generate log: {e}"}

@app.get("/reports/{filename}")
async def download_report_file(filename: str, request: Request):
    """Download a generated session Excel / CSV report."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report file not found.")
        
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if filename.endswith(".xlsx") else "text/csv"
    return FileResponse(filepath, media_type=media_type, filename=filename)

@app.post("/delete_faces")
async def wipe_faces(request: Request):
    """Trigger Full System Reset: AWS + Local Memory + Local Logs."""
    if not is_authenticated(request):
        return {"success": False, "message": "Unauthorized"}

    success, message = delete_all_faces()
    if success:
        attendance_memory.clear()
        PRESENT_IDENTITIES.clear()
        last_seen.clear()
        temporal_memory.clear()
        active_session["attendees"] = []
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f: 
                f.write("Roll Number,Name,Time,Date,Status\n")
        except: pass
        return {"success": True, "message": "Full system reset complete."}
    return {"success": False, "message": message}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
