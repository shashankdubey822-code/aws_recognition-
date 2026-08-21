import os
import time
import secrets
import shutil
import asyncio
import pandas as pd
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, Request, Form, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

# Custom Modules
from core.config import (
    LOG_FILE, REPORTS_DIR, TEACHER_EMAIL, TEACHER_PASSWORD, 
    SESSION_COOKIE_NAME, DEFAULT_SESSION_DURATION_MIN
)
from core.state import (
    attendance_memory, PRESENT_IDENTITIES, last_seen, 
    temporal_memory, active_session, connected_devices
)
from api.websocket import websocket_endpoint, end_active_session, broadcast_json
from api.controllers.event_controller import EventController
from api.controllers import bulk_register_controller as bulk_ctrl
from services.aws_client import ensure_collection_exists, delete_all_faces
from services.email_service import generate_session_excel, get_latest_email_diagnostics

AUTH_TOKEN_VALUE = "teacher_authenticated_valid_session"

# Initialize EventController for 4K batch photo processing
event_controller = EventController(broadcast_func=broadcast_json)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs("static/intruders", exist_ok=True)
    os.makedirs("static/attendees", exist_ok=True)
    os.makedirs("static/raw_frames", exist_ok=True)
    
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
                f.write("Roll Number,Name,Time,Date,Status,Device\n")
            print(f"✅ Created new attendance log: {LOG_FILE}")
    except Exception as e:
        print(f"⚠️ WARNING: Could not load attendance logs: {e}")
    
    yield
    # --- SHUTDOWN PHASE ---
    print("Anyiiiiie.AI Attendance Engine Gracefully Stopped.")

app = FastAPI(title="Anyiiiiie.AI Attendance Engine", lifespan=lifespan)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/raw_frames", StaticFiles(directory="static/raw_frames"), name="raw_frames")
templates = Jinja2Templates(directory="templates")

# WebSocket Route
app.websocket("/ws")(websocket_endpoint)

def is_teacher_authenticated(request: Request) -> bool:
    """Helper to verify teacher authentication from cookie, header, or query token."""
    # 1. Check Query Token parameter (Useful for Iframe embedding)
    token = request.query_params.get("token")
    if token == AUTH_TOKEN_VALUE:
        return True

    # 2. Check Authorization Bearer Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header.split(" ")[1]
        if bearer_token == AUTH_TOKEN_VALUE:
            return True

    # 3. Check Session Cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token == AUTH_TOKEN_VALUE

# --- Web Routes ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Main Instructor Dashboard view with auto-auth detection."""
    is_auth = is_teacher_authenticated(request)
    if not is_auth:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "teacher_email": TEACHER_EMAIL,
        "is_authenticated": is_auth
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render teacher login page."""
    if is_teacher_authenticated(request):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

class LoginPayload(BaseModel):
    email: str
    password: str

@app.post("/api/login")
async def api_login(payload: LoginPayload):
    """JSON Login endpoint designed for Iframes / LocalStorage persistence."""
    if payload.email.strip() == TEACHER_EMAIL and payload.password == TEACHER_PASSWORD:
        response = JSONResponse({
            "success": True, 
            "token": AUTH_TOKEN_VALUE, 
            "email": TEACHER_EMAIL,
            "redirect_url": f"/?token={AUTH_TOKEN_VALUE}"
        })
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=AUTH_TOKEN_VALUE,
            httponly=False,
            samesite="none",
            secure=True,
            max_age=86400 * 7
        )
        return response
    return JSONResponse(status_code=401, content={"success": False, "message": "Invalid email or password"})

@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Handles teacher login form submission."""
    if email.strip() == TEACHER_EMAIL and password == TEACHER_PASSWORD:
        response = RedirectResponse(url=f"/?token={AUTH_TOKEN_VALUE}", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=AUTH_TOKEN_VALUE,
            httponly=False,
            samesite="none",
            secure=True,
            max_age=86400 * 7
        )
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid email or password. Access Denied."
    }, status_code=status.HTTP_401_UNAUTHORIZED)

@app.get("/logout")
async def logout(request: Request):
    """Logs out the teacher and clears session cookie."""
    response = RedirectResponse(url="/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

@app.get("/logs")
async def download_logs(request: Request):
    """Export attendance CSV log."""
    if not os.path.exists(LOG_FILE):
        return {"message": "No attendance records found."}
    
    try:
        df = pd.read_csv(LOG_FILE)
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
@app.get("/api/download_report/{filename}")
async def download_report_file(filename: str, request: Request = None):
    """Download a generated session or event Excel / CSV report."""
    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report file not found.")
        
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if filename.endswith(".xlsx") else "text/csv"
    return FileResponse(filepath, media_type=media_type, filename=filename)

@app.post("/api/event/upload")
async def upload_event_photos(
    background_tasks: BackgroundTasks,
    event_name: str = Form("College Event / Seminar"),
    event_date: str = Form(""),
    event_dept: str = Form("Main Auditorium"),
    photos: list[UploadFile] = File(...)
):
    """Batch upload high-resolution 4K event photos for background multi-tile AI processing."""
    if not photos:
        raise HTTPException(status_code=400, detail="No photos uploaded.")

    event_id = f"evt_{int(time.time())}_{secrets.token_hex(3)}"
    
    # Read files into memory
    file_payloads = []
    for p in photos:
        content = await p.read()
        file_payloads.append({
            "filename": p.filename,
            "bytes": content
        })

    # Start asynchronous event processing pipeline
    background_tasks.add_task(
        event_controller.process_event_batch,
        event_id,
        event_name,
        event_date,
        event_dept,
        file_payloads
    )

    return {
        "success": True,
        "event_id": event_id,
        "event_name": event_name,
        "total_photos": len(photos),
        "message": f"Successfully received {len(photos)} event photos. 4K Sliced AI processing initiated."
    }

@app.get("/api/email_diagnostics", response_class=PlainTextResponse)
async def get_email_error_diagnostics():
    """Dedicated error diagnosis file viewer for email dispatching."""
    return get_latest_email_diagnostics()

@app.post("/api/clear_frames")
async def clear_raw_frames(request: Request):
    """Purge all stored raw uncropped frames and reset device frame buffers."""
    try:
        if os.path.exists("static/raw_frames"):
            shutil.rmtree("static/raw_frames")
            os.makedirs("static/raw_frames", exist_ok=True)
        
        for dev_id in connected_devices:
            connected_devices[dev_id]["raw_frames"] = []
            connected_devices[dev_id]["cropped_queue"] = []
            connected_devices[dev_id]["total_frames"] = 0
            
        return {"success": True, "message": "Raw frame cache cleared successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/delete_faces")
async def wipe_faces(request: Request):
    """Trigger Full System Reset: AWS + Local Memory + Local Logs."""
    success, message = delete_all_faces()
    if success:
        attendance_memory.clear()
        PRESENT_IDENTITIES.clear()
        last_seen.clear()
        temporal_memory.clear()
        active_session["attendees"] = []
        for dev_id in connected_devices:
            connected_devices[dev_id]["verified_students"] = []
            connected_devices[dev_id]["raw_frames"] = []
            connected_devices[dev_id]["cropped_queue"] = []
            connected_devices[dev_id]["total_frames"] = 0
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f: 
                f.write("Roll Number,Name,Time,Date,Status,Device\n")
        except: pass
        return {"success": True, "message": "Full system reset complete."}
    return {"success": False, "message": message}

# ─────────────────────────────────────────────────────────────────────────────
# BULK SMART REGISTRATION — 5-Step Pipeline Endpoints
# ADDITIVE ONLY — never deletes existing registered students
# ─────────────────────────────────────────────────────────────────────────────

class BulkClusterRequest(BaseModel):
    session_id: str

class BulkRemoveCropRequest(BaseModel):
    session_id: str
    cluster_id: str
    crop_id: str

class BulkPushPersonRequest(BaseModel):
    session_id: str
    cluster_id: str
    person_name: str
    person_roll: str = ""

class BulkPushAllRequest(BaseModel):
    session_id: str
    labels: list  # [{cluster_id, person_name, person_roll}]


@app.post("/api/bulk/crop")
async def bulk_crop_images(
    photos: list[UploadFile] = File(...)
):
    """
    STEP 2 — Crop all faces from uploaded 4K auditorium photos.
    Returns session_id + all detected face crops as base64.
    Does NOT write to AWS or SQLite.
    """
    if not photos:
        raise HTTPException(status_code=400, detail="No photos uploaded.")

    file_payloads = []
    for p in photos:
        content = await p.read()
        file_payloads.append({"filename": p.filename, "bytes": content})

    result = await bulk_ctrl.crop_images(file_payloads)
    return result


@app.post("/api/bulk/cluster")
async def bulk_cluster_faces(req: BulkClusterRequest):
    """
    STEP 3 — Group all crops from the session into person clusters.
    Uses AWS Rekognition compare_faces() — read-only, no writes to collection.
    Returns clusters labeled Unknown #1, Unknown #2, ...
    """
    result = await bulk_ctrl.cluster_faces(req.session_id)
    return result


@app.post("/api/bulk/remove_crop")
async def bulk_remove_crop(req: BulkRemoveCropRequest):
    """
    STEP 3b — Remove a specific crop from a cluster (user correction).
    If user thinks algorithm merged two different people, they can remove wrong crops.
    """
    result = bulk_ctrl.remove_crop_from_cluster(
        req.session_id, req.cluster_id, req.crop_id
    )
    return result


@app.post("/api/bulk/push_person")
async def bulk_push_person(req: BulkPushPersonRequest):
    """
    STEP 5 — Push ONE labeled person cluster to AWS Rekognition.
    Pushes top-3 best quality crops as face vectors.
    Saves to SQLite registered_faces table.
    User must click — never automatic.
    SAFE: uses index_faces() (append only), never deletes existing data.
    """
    result = await bulk_ctrl.push_person_to_aws(
        req.session_id, req.cluster_id, req.person_name, req.person_roll
    )
    return result


@app.post("/api/bulk/push_all")
async def bulk_push_all(req: BulkPushAllRequest):
    """
    STEP 5b — Push ALL labeled clusters to AWS Rekognition at once.
    Skips clusters with empty names or already pushed.
    User must click — never automatic.
    """
    result = await bulk_ctrl.push_all_to_aws(req.session_id, req.labels)
    return result


@app.post("/api/bulk/clear_session")
async def bulk_clear_session(req: BulkClusterRequest):
    """Free server-side memory for a completed bulk session."""
    bulk_ctrl.clear_session(req.session_id)
    return {"success": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
