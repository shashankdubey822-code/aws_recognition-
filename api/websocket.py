import json
import os
import time
import base64
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

os.makedirs("static/intruders", exist_ok=True)
os.makedirs("static/attendees", exist_ok=True)
os.makedirs("static/raw_frames", exist_ok=True)

from services.liveness_engine import warmup
from services.email_service import send_session_email_report
from api.controllers.registration_controller import RegistrationController
from api.controllers.tracking_controller import TrackingController
from core.state import active_session, last_seen, PRESENT_IDENTITIES, connected_devices

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
    
    # Mark active devices as standby
    for dev_id in connected_devices:
        if connected_devices[dev_id]["status"] == "active":
            connected_devices[dev_id]["status"] = "standby"
    
    print(f"[SESSION] 🛑 Concluding session {session_id}. Total attendees: {total_present}. Reason: {reason}")
    
    # Broadcast session stopped to UI and Raspberry Pi
    await broadcast_json({
        "type": "session_stopped",
        "session_id": session_id,
        "total_attendees": total_present,
        "reason": reason
    })

    # Broadcast updated devices list
    await broadcast_json({
        "type": "devices_update",
        "devices": list(connected_devices.values())
    })

    # Trigger Async Email Report Dispatch
    session_snapshot = dict(active_session)
    session_snapshot["attendees"] = list(active_session["attendees"])
    
    asyncio.create_task(asyncio.to_thread(send_session_email_report, session_snapshot))

def save_raw_frame(device_id: str, image_bytes: bytes) -> str:
    """Saves raw uncropped frame to disk and returns web URL."""
    try:
        clean_dev = "".join(c for c in device_id if c.isalnum() or c in ('_', '-'))
        dev_dir = os.path.join("static/raw_frames", clean_dev)
        os.makedirs(dev_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        filename = f"raw_{timestamp}.jpg"
        filepath = os.path.join(dev_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(image_bytes)
            
        return f"/static/raw_frames/{clean_dev}/{filename}"
    except Exception as e:
        print(f"⚠️ Failed to save raw frame: {e}")
        return ""

async def websocket_endpoint(websocket: WebSocket):
    global session_timer_task
    await websocket.accept()
    active_connections.add(websocket)
    
    # Extract Client IP
    forwarded_for = websocket.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif websocket.client:
        client_ip = websocket.client.host
    else:
        client_ip = "Unknown IP"

    assigned_device_id = "web_demo_client"
    
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
    
    # Send initial devices list
    await websocket.send_json({
        "type": "devices_update",
        "devices": list(connected_devices.values())
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
                    
                    # Clean slate: Fresh session starts from 0 students
                    last_seen.clear()
                    PRESENT_IDENTITIES.clear()
                    
                    active_session["id"] = session_id
                    active_session["active"] = True
                    active_session["duration_minutes"] = duration
                    active_session["start_time"] = time.time()
                    active_session["end_time"] = None
                    active_session["attendees"] = []
                    
                    # Reset per-device verified students for this fresh session
                    for dev_id in connected_devices:
                        if connected_devices[dev_id]["status"] != "disconnected":
                            connected_devices[dev_id]["status"] = "active"
                        connected_devices[dev_id]["verified_students"] = []
                    
                    # Cancel any existing timer
                    if session_timer_task and not session_timer_task.done():
                        session_timer_task.cancel()
                    
                    # Schedule auto-stop timer
                    session_timer_task = asyncio.create_task(auto_stop_session_timer(duration * 60))
                    
                    print(f"[SESSION] ▶️ Started fresh session {session_id} for {duration} minutes.")
                    
                    # Notify all clients (UI + Raspberry Pi)
                    await broadcast_json({
                        "type": "session_started",
                        "session_id": session_id,
                        "duration_minutes": duration,
                        "start_time": active_session["start_time"],
                        "reset_attendance": True
                    })
                    
                    await broadcast_json({
                        "type": "devices_update",
                        "devices": list(connected_devices.values())
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

                # --- 2. Edge Device Registration (Multi-Classroom Support) ---
                if p_type == "edge_register":
                    device_name = payload.get("device", "Raspberry Pi Edge")
                    dev_id = payload.get("device_id") or f"rpi_{device_name.replace(' ', '_').lower()}"
                    assigned_device_id = dev_id
                    
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if dev_id not in connected_devices:
                        connected_devices[dev_id] = {
                            "device_id": dev_id,
                            "device_name": device_name,
                            "client_ip": client_ip,
                            "status": "active" if active_session.get("active") else "standby",
                            "first_seen": now_str,
                            "last_seen": now_str,
                            "total_frames": 0,
                            "raw_frames": [],
                            "verified_students": []
                        }
                    else:
                        connected_devices[dev_id]["device_name"] = device_name
                        connected_devices[dev_id]["client_ip"] = client_ip
                        connected_devices[dev_id]["status"] = "active" if active_session.get("active") else "standby"
                        connected_devices[dev_id]["last_seen"] = now_str

                    print(f"[EDGE] 📡 Registered: {device_name} (ID: {dev_id}, IP: {client_ip})")
                    
                    await websocket.send_json({
                        "type": "edge_ack",
                        "session_active": active_session.get("active", False),
                        "duration_minutes": active_session.get("duration_minutes", 50)
                    })
                    
                    await broadcast_json({
                        "type": "devices_update",
                        "devices": list(connected_devices.values())
                    })
                    continue

                # --- 3. Live Tracking Frame (With Controlled Raw Frame Storage) ---
                if p_type == "frame":
                    dev_id = payload.get("device_id") or assigned_device_id
                    dev_name = payload.get("device_name") or (connected_devices.get(dev_id, {}).get("device_name", "Edge Camera"))
                    
                    # Update device telemetry
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if dev_id not in connected_devices:
                        connected_devices[dev_id] = {
                            "device_id": dev_id,
                            "device_name": dev_name,
                            "client_ip": client_ip,
                            "status": "active",
                            "first_seen": now_str,
                            "last_seen": now_str,
                            "total_frames": 0,
                            "raw_frames": [],
                            "verified_students": []
                        }
                    else:
                        connected_devices[dev_id]["last_seen"] = now_str
                        connected_devices[dev_id]["status"] = "active"
                    
                    connected_devices[dev_id]["total_frames"] += 1
                    
                    # Save raw uncropped frame selectively (only for edge devices or during active session)
                    if dev_id.startswith("rpi_") or active_session.get("active"):
                        try:
                            encoded_data = payload["image"].split(',')[1]
                            raw_bytes = base64.b64decode(encoded_data)
                            raw_url = save_raw_frame(dev_id, raw_bytes)
                            
                            if raw_url:
                                frame_entry = {
                                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                    "url": raw_url,
                                    "device_id": dev_id,
                                    "device_name": dev_name,
                                    "ip": client_ip
                                }
                                connected_devices[dev_id]["raw_frames"].insert(0, frame_entry)
                                if len(connected_devices[dev_id]["raw_frames"]) > 20:
                                    connected_devices[dev_id]["raw_frames"].pop()
                                    
                                await broadcast_json({
                                    "type": "new_raw_frame",
                                    "device_id": dev_id,
                                    "frame": frame_entry
                                })
                        except Exception as fe:
                            print(f"⚠️ Raw frame extraction error: {fe}")

                    # Continue standard tracking & face detection pipeline
                    await tracking_controller.process_frame(payload)
                    continue

                # --- 4. Registration Messages ---
                if p_type == "start_registration":
                    registration_controller.start_registration(payload)
                    continue

                if p_type == "register_frame":
                    await registration_controller.process_frame(payload)
                    continue

                # --- 5. Query Devices List ---
                if p_type == "get_devices":
                    await websocket.send_json({
                        "type": "devices_update",
                        "devices": list(connected_devices.values())
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
        if assigned_device_id in connected_devices:
            connected_devices[assigned_device_id]["status"] = "standby"
            asyncio.create_task(broadcast_json({
                "type": "devices_update",
                "devices": list(connected_devices.values())
            }))
