"""
api/websocket.py - Real-Time WebSocket Controller with Multi-Device Targeting, Flush Queue Protection & 24-Hour IST.
Handles bi-directional communication with edge hardware and browser dashboard.
"""

import sys
import os
import json
import time
import base64
import asyncio
from typing import Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.state import (
    active_connections,
    connected_devices,
    active_session,
    last_seen,
    PRESENT_IDENTITIES
)
from core.timezone_utils import (
    get_time_str,
    get_date_str,
    get_timestamp_full_str,
    get_compact_timestamp_str
)
from services.attendance import mark_attendance
from services.email_service import send_session_email_report
from api.controllers.registration_controller import RegistrationController
from api.controllers.tracking_controller import TrackingController

router = APIRouter()

session_timer_task = None


async def broadcast_json(data: dict):
    """Broadcasts JSON payload to all active browser connections."""
    dead_connections = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            dead_connections.add(ws)
    
    for dead in dead_connections:
        active_connections.discard(dead)


async def auto_stop_session_timer(duration_seconds: int):
    """Timer coroutine that automatically stops monitoring when the class duration expires."""
    try:
        await asyncio.sleep(duration_seconds)
        print(f"[SESSION] ⏰ Class session duration ({duration_seconds//60} mins) elapsed. Automatically wrapping up...")
        await end_active_session("Class Period Concluded")
    except asyncio.CancelledError:
        pass


async def wait_for_in_flight_aws_scans(max_wait_seconds: float = 6.0):
    """
    Queue Flush Guard: Waits until all in-flight face crops in the FIFO queue 
    have finished contacting AWS and received their final label ('match', 'no_match', or 'error') 
    BEFORE compiling and emailing the final attendance report.
    """
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        pending_count = 0
        for dev_id, dev_data in connected_devices.items():
            queue = dev_data.get("cropped_queue", [])
            for item in queue:
                if item.get("status") == "scanning":
                    pending_count += 1
            if dev_data.get("stage") == "AWS_MATCHING":
                pending_count += 1

        if pending_count == 0:
            break
        
        print(f"[SESSION FLUSH] ⏳ Waiting for {pending_count} pending face scans to complete before emailing report...")
        await asyncio.sleep(0.5)


async def end_active_session(reason: str = "Teacher Manual Stop"):
    """
    Terminates the active class session:
    1. Sends stop command to edge nodes to immediately halt further camera captures.
    2. Gracefully awaits any in-flight AWS face verifications to finish and label.
    3. Gathers the complete verified attendance ledger.
    4. Triggers asynchronous background task to compile Excel and deliver email report via Resend HTTPS REST API.
    5. Broadcasts session completion status to all connected dashboards.
    """
    global session_timer_task
    
    if session_timer_task and not session_timer_task.done():
        session_timer_task.cancel()
        session_timer_task = None

    session_id = active_session.get("id", f"SES_{get_compact_timestamp_str()}")
    active_session["active"] = False
    active_session["finishing"] = True

    print(f"[SESSION] 🛑 Concluding session {session_id}. Reason: {reason}. Waiting for in-flight face scans (24h IST: {get_time_str()})...")

    # 1. First signal edge cameras to stop capturing new frames
    for dev_id in connected_devices:
        connected_devices[dev_id]["status"] = "standby"

    await broadcast_json({
        "type": "devices_update",
        "devices": list(connected_devices.values())
    })

    # 2. FLUSH IN-FLIGHT SCANS: Guarantee every detected face gets labeled before email is built
    await wait_for_in_flight_aws_scans(max_wait_seconds=6.0)

    # 3. Consolidate final verified attendees from session state and connected device logs
    attendee_map = {}
    for att in active_session.get("attendees", []):
        if att.get("name") and att.get("name") != "Unknown":
            k = (att.get("name"), att.get("roll_number"))
            attendee_map[k] = att

    for dev_id, dev_data in connected_devices.items():
        for st in dev_data.get("verified_students", []):
            if st.get("name") and st.get("name") != "Unknown":
                k = (st.get("name"), st.get("roll_number"))
                if k not in attendee_map:
                    attendee_map[k] = {
                        "roll_number": st.get("roll_number", "N/A"),
                        "name": st.get("name"),
                        "time": st.get("time", get_time_str()),
                        "date": get_date_str(),
                        "photo": st.get("photo", ""),
                        "device_id": dev_data.get("device_name", dev_id)
                    }

    attendees = list(attendee_map.values())
    active_session["attendees"] = attendees
    active_session["finishing"] = False
    active_session["end_time"] = time.time()

    # 4. Broadcast final stop status to UI
    await broadcast_json({
        "type": "session_stopped",
        "session_id": session_id,
        "reason": reason,
        "total_attendees": len(attendees),
        "end_time": active_session["end_time"]
    })

    for dev_id in connected_devices:
        connected_devices[dev_id]["stage"] = "IDLE"

    await broadcast_json({
        "type": "devices_update",
        "devices": list(connected_devices.values())
    })

    # 5. Gather all raw uncropped frames captured during session
    raw_frames = list(active_session.get("session_raw_frames", []))
    if not raw_frames:
        for dev_id, dev_data in connected_devices.items():
            for frm in dev_data.get("raw_frames", []):
                u = frm.get("url", "")
                p = u[1:] if u.startswith("/") else u
                if p and p not in raw_frames and os.path.exists(p):
                    raw_frames.append(p)

    # 6. Asynchronously dispatch final compiled email report with Excel & full uncropped frames via HTTPS REST API
    session_data = {
        "id": session_id,
        "attendees": attendees,
        "duration_minutes": active_session.get("duration_minutes", 50),
        "raw_frames": raw_frames
    }
    
    async def _async_email_task():
        success, msg = await asyncio.to_thread(send_session_email_report, session_data)
        print(f"[SESSION EMAIL] {msg}")

    asyncio.create_task(_async_email_task())


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global session_timer_task
    
    await websocket.accept()
    active_connections.add(websocket)
    
    reg_controller = RegistrationController(websocket)
    tracking_controller = TrackingController(websocket, broadcast_func=broadcast_json)
    
    registered_edge_id = None
    client_ip = websocket.client.host if websocket.client else "127.0.0.1"

    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                continue

            try:
                payload = json.loads(data)
                p_type = payload.get("type")

                # --- 1. Multi-Device Targeted Session Control Triggers ---
                if p_type == "start_session":
                    duration = int(payload.get("duration_minutes", 50))
                    target_device = payload.get("target_device", "")
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
                    active_session["session_raw_frames"] = []
                    active_session["target_device"] = target_device
                    
                    # Reset per-device verified students and set status according to target
                    for dev_id in connected_devices:
                        is_target = (not target_device or target_device == "ALL" or target_device == dev_id)
                        if connected_devices[dev_id]["status"] != "disconnected":
                            connected_devices[dev_id]["status"] = "active" if is_target else "standby"
                        connected_devices[dev_id]["verified_students"] = []
                        connected_devices[dev_id]["cropped_queue"] = []
                    
                    if session_timer_task and not session_timer_task.done():
                        session_timer_task.cancel()
                    
                    session_timer_task = asyncio.create_task(auto_stop_session_timer(duration * 60))
                    
                    print(f"[SESSION] ▶️ Started session {session_id} for {duration} mins. Target: {target_device} (24h IST: {get_time_str()}).")
                    
                    await broadcast_json({
                        "type": "session_started",
                        "session_id": session_id,
                        "duration_minutes": duration,
                        "target_device": target_device,
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
                    remaining_sec = 0
                    if active_session.get("active") and active_session.get("start_time"):
                        elapsed = time.time() - active_session["start_time"]
                        total_dur = active_session.get("duration_minutes", 50) * 60
                        remaining_sec = max(0, int(total_dur - elapsed))

                    await websocket.send_text(json.dumps({
                        "type": "session_status",
                        "active": active_session.get("active", False),
                        "session_id": active_session.get("id"),
                        "remaining_seconds": remaining_sec,
                        "target_device": active_session.get("target_device", ""),
                        "total_attendees": len(active_session.get("attendees", []))
                    }))
                    continue

                # --- 2. Edge Hardware Device Handshake & Registration ---
                if p_type == "edge_register":
                    dev_name = payload.get("device", "Raspberry Pi Node")
                    dev_id = payload.get("device_id", f"rpi_{dev_name.replace(' ', '_').lower()}")
                    registered_edge_id = dev_id
                    
                    first_time = get_time_str()
                    if dev_id not in connected_devices:
                        connected_devices[dev_id] = {
                            "device_id": dev_id,
                            "device_name": dev_name,
                            "client_ip": payload.get("ip", client_ip),
                            "status": "standby",
                            "stage": "IDLE",
                            "first_seen": first_time,
                            "last_seen": first_time,
                            "total_frames": 0,
                            "raw_frames": [],
                            "cropped_queue": [],
                            "verified_students": [],
                            "telemetry": payload.get("telemetry", {})
                        }
                    else:
                        connected_devices[dev_id]["status"] = "standby"
                        connected_devices[dev_id]["last_seen"] = first_time
                        connected_devices[dev_id]["telemetry"] = payload.get("telemetry", {})

                    print(f"[EDGE NODE] 🔌 Node connected: '{dev_name}' (ID: {dev_id}, IP: {client_ip}) at {first_time} IST")
                    
                    is_active = active_session.get("active", False)
                    target = active_session.get("target_device", "")
                    should_stream = is_active and (not target or target == "ALL" or target == dev_id)

                    await websocket.send_text(json.dumps({
                        "type": "edge_ack",
                        "status": "registered",
                        "device_id": dev_id,
                        "session_active": should_stream,
                        "duration_minutes": active_session.get("duration_minutes", 50),
                        "server_time_24h": get_time_str()
                    }))
                    
                    await broadcast_json({
                        "type": "devices_update",
                        "devices": list(connected_devices.values())
                    })
                    continue

                # --- 3. Telemetry Query ---
                if p_type == "get_devices":
                    await websocket.send_text(json.dumps({
                        "type": "devices_update",
                        "devices": list(connected_devices.values())
                    }))
                    continue

                # --- 4. Biometric Student 3D Scanning ---
                if p_type == "start_registration":
                    reg_controller.start_registration(payload)
                    continue

                if p_type == "register_frame":
                    await reg_controller.process_frame(payload)
                    continue

                # --- 5. Surveillance Tracking Frame Ingestion ---
                if p_type == "frame":
                    is_demo = payload.get("is_demo", False)
                    dev_id = payload.get("device_id", registered_edge_id or "web_demo")
                    
                    # Only process frames if session is active (or if it's the live demo modal)
                    target = active_session.get("target_device", "")
                    is_target = (not target or target == "ALL" or target == dev_id)

                    if not is_demo and (not active_session.get("active") or not is_target):
                        continue

                    await tracking_controller.process_frame(payload)
                    continue

                if p_type == "heartbeat":
                    await websocket.send_text(json.dumps({"type": "pong", "time": get_time_str()}))
                    continue

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"[WS ERROR] Error processing message: {e}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS DISCONNECT] Socket closed: {e}")
    finally:
        active_connections.discard(websocket)
        if registered_edge_id and registered_edge_id in connected_devices:
            connected_devices[registered_edge_id]["status"] = "disconnected"
            print(f"[EDGE NODE] ❌ Edge device '{registered_edge_id}' went offline.")
            await broadcast_json({
                "type": "devices_update",
                "devices": list(connected_devices.values())
            })
