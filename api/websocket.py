import json
import os
import time
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

os.makedirs("static/intruders", exist_ok=True)
os.makedirs("static/attendees", exist_ok=True)

from services.liveness_engine import warmup
from services.email_service import send_session_email_report
from api.controllers.registration_controller import RegistrationController
from api.controllers.tracking_controller import TrackingController
from core.state import active_session

# Pre-warm MiniFASNet model into RAM on startup
try:
    warmup()
except Exception as e:
    print(f"[LIVENESS] Warmup skipped: {e}")

# Connected WebSocket clients (UI + Raspberry Pi)
active_connections: set[WebSocket] = set()
session_timer_task: asyncio.Task | None = None

async def broadcast_json(data: dict):
    """Broadcasts a JSON message to all connected clients."""
    disconnected = set()
    for ws in list(active_connections):
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        active_connections.discard(ws)

async def auto_stop_session_timer(duration_seconds: float):
    """Background task that counts down and stops session automatically."""
    try:
        await asyncio.sleep(duration_seconds)
        if active_session.get("active"):
            print(f"[SESSION] ⏰ Duration elapsed ({active_session['duration_minutes']} min). Concluding session automatically.")
            await end_active_session("Timer Expired")
    except asyncio.CancelledError:
        pass

async def end_active_session(reason: str = "Manual Stop"):
    """Concludes the active monitoring session, generates reports, and sends email."""
    global session_timer_task
    if session_timer_task and not session_timer_task.done():
        session_timer_task.cancel()
        session_timer_task = None

    if not active_session.get("active"):
        return

    active_session["active"] = False
    active_session["end_time"] = time.time()
    
    total_present = len(active_session.get("attendees", []))
    session_id = active_session.get("id", "SESSION")
    
    print(f"[SESSION] 🛑 Concluding session {session_id}. Total attendees: {total_present}. Reason: {reason}")
    
    # Broadcast session stopped to UI and Raspberry Pi
    await broadcast_json({
        "type": "session_stopped",
        "session_id": session_id,
        "total_attendees": total_present,
        "reason": reason
    })

    # Trigger Async Email Report Dispatch
    session_snapshot = dict(active_session)
    session_snapshot["attendees"] = list(active_session["attendees"])
    
    asyncio.create_task(asyncio.to_thread(send_session_email_report, session_snapshot))

async def websocket_endpoint(websocket: WebSocket):
    global session_timer_task
    await websocket.accept()
    active_connections.add(websocket)
    
    registration_controller = RegistrationController(websocket)
    tracking_controller = TrackingController(websocket)
    
    # Send initial session state upon connection
    if active_session.get("active"):
        elapsed = time.time() - (active_session.get("start_time") or time.time())
        remaining = max(0, (active_session["duration_minutes"] * 60) - elapsed)
        await websocket.send_json({
            "type": "session_status",
            "active": True,
            "session_id": active_session.get("id"),
            "duration_minutes": active_session.get("duration_minutes", 50),
            "remaining_seconds": int(remaining),
            "total_attendees": len(active_session.get("attendees", []))
        })
    else:
        await websocket.send_json({
            "type": "session_status",
            "active": False
        })
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                payload = json.loads(data)
                p_type = payload.get("type")

                # --- 1. Session Control Triggers ---
                if p_type == "start_session":
                    duration = int(payload.get("duration_minutes", 50))
                    session_id = f"SES_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    active_session["id"] = session_id
                    active_session["active"] = True
                    active_session["duration_minutes"] = duration
                    active_session["start_time"] = time.time()
                    active_session["end_time"] = None
                    active_session["attendees"] = []
                    
                    # Cancel any existing timer
                    if session_timer_task and not session_timer_task.done():
                        session_timer_task.cancel()
                    
                    # Schedule auto-stop timer
                    session_timer_task = asyncio.create_task(auto_stop_session_timer(duration * 60))
                    
                    print(f"[SESSION] ▶️ Started session {session_id} for {duration} minutes.")
                    
                    # Notify all clients (UI + Raspberry Pi)
                    await broadcast_json({
                        "type": "session_started",
                        "session_id": session_id,
                        "duration_minutes": duration,
                        "start_time": active_session["start_time"]
                    })
                    continue

                if p_type == "stop_session":
                    await end_active_session("Teacher Stopped")
                    continue

                if p_type == "get_session_status":
                    if active_session.get("active"):
                        elapsed = time.time() - (active_session.get("start_time") or time.time())
                        remaining = max(0, (active_session["duration_minutes"] * 60) - elapsed)
                        await websocket.send_json({
                            "type": "session_status",
                            "active": True,
                            "session_id": active_session.get("id"),
                            "duration_minutes": active_session.get("duration_minutes"),
                            "remaining_seconds": int(remaining),
                            "total_attendees": len(active_session.get("attendees", []))
                        })
                    else:
                        await websocket.send_json({
                            "type": "session_status",
                            "active": False
                        })
                    continue

                # --- 2. Registration Messages ---
                if p_type == "start_registration":
                    registration_controller.start_registration(payload)
                    continue

                if p_type == "register_frame":
                    await registration_controller.process_frame(payload)
                    continue

                # --- 3. Live Tracking Frame ---
                if p_type == "frame":
                    await tracking_controller.process_frame(payload)
                    continue

                # --- 4. Edge Device Register ---
                if p_type == "edge_register":
                    device_name = payload.get("device", "RaspberryPi")
                    print(f"[EDGE] 📡 Edge device connected: {device_name}")
                    await websocket.send_json({
                        "type": "edge_ack",
                        "session_active": active_session.get("active", False),
                        "duration_minutes": active_session.get("duration_minutes", 50)
                    })
                    continue

            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "close" in str(e).lower():
                    break
                print(f"Frame Error: {e}")
                try: await websocket.send_json({"type": "error", "message": f"Frame Error: {str(e)}"})
                except: pass
            except Exception as e:
                print(f"Frame Processing Error: {e}")
                try: await websocket.send_json({"type": "error", "message": f"Frame Error: {str(e)}"})
                except: pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS Fatal Error: {e}")
    finally:
        active_connections.discard(websocket)
