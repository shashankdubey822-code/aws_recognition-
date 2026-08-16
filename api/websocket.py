"""
api/websocket.py - Real-Time WebSocket Controller with Multi-Device Targeting & 24-Hour IST.
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


async def end_active_session(reason: str = "Teacher Manual Stop"):
    """
    Terminates the active class session:
    1. Sends stop command to all or targeted Raspberry Pi edge nodes.
    2. Gathers verified session attendance.
    3. Triggers asynchronous background task to compile Excel and deliver email report.
    4. Broadcasts session completion status to all connected dashboards.
    """
    global session_timer_task
    
    if session_timer_task and not session_timer_task.done():
        session_timer_task.cancel()
        session_timer_task = None

    if not active_session.get("active"):
        return

    session_id = active_session.get("id", f"SES_{get_compact_timestamp_str()}")
    active_session["active"] = False
    active_session["end_time"] = time.time()
    attendees = list(active_session.get("attendees", []))

    print(f"[SESSION] 🛑 Concluding session {session_id}. Reason: {reason}. Total Present: {len(attendees)} (24h IST: {get_time_str()})")

    # Broadcast stop command to edge nodes and browser clients
    await broadcast_json({
        "type": "session_stopped",
        "session_id": session_id,
        "reason": reason,
        "total_attendees": len(attendees),
        "end_time": active_session["end_time"]
    })

    # Reset per-device status
    for dev_id in connected_devices:
        connected_devices[dev_id]["status"] = "standby"
        connected_devices[dev_id]["stage"] = "IDLE"

    await broadcast_json({
        "type": "devices_update",
        "devices": list(connected_devices.values())
    })

    # Asynchronously dispatch email report via HTTPS REST API (Port 443)
    asyncio.create_task(
        send_session_email_report(
            session_id=session_id,
            attendees=attendees,
            duration_minutes=active_session.get("duration_minutes", 50)
        )
    )


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
                    target_device = payload.get("target_device", "ALL")
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
                    active_session["target_device"] = target_device
                    
                    # Reset per-device verified students and set status according to target
                    for dev_id in connected_devices:
                        is_target = (target_device == "ALL" or target_device == dev_id)
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
                        "target_device": active_session.get("target_device", "ALL"),
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
                    target = active_session.get("target_device", "ALL")
                    should_stream = is_active and (target == "ALL" or target == dev_id)

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
                    target = active_session.get("target_device", "ALL")
                    is_target = (target == "ALL" or target == dev_id)

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
