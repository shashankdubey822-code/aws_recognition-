import os
import json
import time
import base64
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from core.state import active_connections, connected_devices, active_session, attendance_memory, last_seen, PRESENT_IDENTITIES
from core.timezone_utils import get_time_str, get_date_str, get_timestamp_full_str, get_compact_timestamp_str
from api.controllers.registration_controller import RegistrationController
from api.controllers.tracking_controller import TrackingController
from services.email_service import send_session_email_report

session_timer_task = None

async def broadcast_json(message: dict):
    """Broadcasts a JSON message to all active WebSocket connections (UI dashboards and Pi nodes)."""
    dead_connections = set()
    for ws in list(active_connections):
        try:
            await ws.send_json(message)
        except Exception:
            dead_connections.add(ws)
    for ws in dead_connections:
        active_connections.discard(ws)

async def auto_stop_session_timer(duration_seconds: int):
    """Asynchronous background worker that concludes session when duration expires."""
    try:
        await asyncio.sleep(duration_seconds)
        if active_session.get("active"):
            await end_active_session("Timer Expired")
    except asyncio.CancelledError:
        pass

async def end_active_session(reason: str = "Concluded"):
    """Handles end of session, status resets, and automatic report dispatch to shashankdubey822@gmail.com."""
    global session_timer_task
    
    if not active_session.get("active"):
        return
        
    if session_timer_task and not session_timer_task.done():
        session_timer_task.cancel()
        
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
        
        timestamp = get_compact_timestamp_str()
        micro = int(time.time() * 1000) % 1000
        filename = f"raw_{timestamp}_{micro:03d}.jpg"
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
    
    forwarded_for = websocket.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif websocket.client:
        client_ip = websocket.client.host
    else:
        client_ip = "Unknown IP"

    assigned_device_id = "web_demo_client"
    
    registration_controller = RegistrationController(websocket)
    tracking_controller = TrackingController(websocket, broadcast_func=broadcast_json)
    
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

    try:
        while True:
            try:
                data = await websocket.receive_text()
                payload = json.loads(data)
                p_type = payload.get("type")

                # --- 1. Session Control Triggers ---
                if p_type == "start_session":
                    duration = int(payload.get("duration_minutes", 50))
                    session_id = f"SES_{get_compact_timestamp_str()}"
                    
                    # Clean slate: Fresh session starts from 0 students
                    last_seen.clear()
                    PRESENT_IDENTITIES.clear()
                    
                    active_session["id"] = session_id
                    active_session["active"] = True
                    active_session["duration_minutes"] = duration
                    active_session["start_time"] = time.time()
                    active_session["end_time"] = None
                    active_session["attendees"] = []
                    
                    # Reset per-device verified students and cropped queue for this fresh session
                    for dev_id in connected_devices:
                        if connected_devices[dev_id]["status"] != "disconnected":
                            connected_devices[dev_id]["status"] = "active"
                        connected_devices[dev_id]["verified_students"] = []
                        connected_devices[dev_id]["cropped_queue"] = []
                    
                    if session_timer_task and not session_timer_task.done():
                        session_timer_task.cancel()
                    
                    session_timer_task = asyncio.create_task(auto_stop_session_timer(duration * 60))
                    
                    print(f"[SESSION] ▶️ Started fresh session {session_id} for {duration} minutes (24h IST: {get_time_str()}).")
                    
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
                            "active": False,
                            "remaining_seconds": 0
                        })
                    continue

                # --- 2. Edge Device Registration ---
                if p_type == "edge_register":
                    device_name = payload.get("device", "Raspberry Pi Edge")
                    dev_id = payload.get("device_id") or f"rpi_{device_name.replace(' ', '_').lower()}"
                    assigned_device_id = dev_id
                    
                    now_str = get_timestamp_full_str()
                    
                    if dev_id not in connected_devices:
                        connected_devices[dev_id] = {
                            "device_id": dev_id,
                            "device_name": device_name,
                            "client_ip": client_ip,
                            "status": "active" if active_session.get("active") else "standby",
                            "stage": "IDLE",
                            "first_seen": now_str,
                            "last_seen": now_str,
                            "total_frames": 0,
                            "raw_frames": [],
                            "cropped_queue": [],
                            "verified_students": []
                        }
                    else:
                        connected_devices[dev_id]["device_name"] = device_name
                        connected_devices[dev_id]["client_ip"] = client_ip
                        connected_devices[dev_id]["status"] = "active" if active_session.get("active") else "standby"
                        connected_devices[dev_id]["last_seen"] = now_str

                    print(f"[EDGE] 📡 Registered: {device_name} (ID: {dev_id}, IP: {client_ip}) at {get_time_str()} IST")
                    
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

                # --- 3. Live Tracking Frame ---
                if p_type == "frame":
                    dev_id = payload.get("device_id") or assigned_device_id
                    dev_name = payload.get("device_name") or (connected_devices.get(dev_id, {}).get("device_name", "Edge Camera"))
                    
                    now_str = get_timestamp_full_str()
                    if dev_id not in connected_devices:
                        connected_devices[dev_id] = {
                            "device_id": dev_id,
                            "device_name": dev_name,
                            "client_ip": client_ip,
                            "status": "active",
                            "stage": "IDLE",
                            "first_seen": now_str,
                            "last_seen": now_str,
                            "total_frames": 0,
                            "raw_frames": [],
                            "cropped_queue": [],
                            "verified_students": []
                        }
                    else:
                        connected_devices[dev_id]["last_seen"] = now_str
                        connected_devices[dev_id]["status"] = "active"
                    
                    connected_devices[dev_id]["total_frames"] += 1
                    
                    # Save raw uncropped frame selectively
                    if dev_id.startswith("rpi_") or active_session.get("active"):
                        try:
                            encoded_data = payload["image"].split(',')[1]
                            raw_bytes = base64.b64decode(encoded_data)
                            raw_url = save_raw_frame(dev_id, raw_bytes)
                            
                            if raw_url:
                                frame_entry = {
                                    "timestamp": get_time_str(),
                                    "date": get_date_str(),
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

                    # Run async face detection, cropping, and AWS Rekognition verification
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
            except Exception as e:
                print(f"WS Handling error: {e}")

    finally:
        active_connections.discard(websocket)
        if assigned_device_id and assigned_device_id in connected_devices:
            connected_devices[assigned_device_id]["status"] = "standby"
            await broadcast_json({
                "type": "devices_update",
                "devices": list(connected_devices.values())
            })
