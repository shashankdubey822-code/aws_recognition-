import json
import base64
import time
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_ultra

registration_sessions = {}

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "start_registration":
                name = payload.get("name")
                registration_sessions[websocket] = {"name": name, "frames": 0, "stage": "CENTER"}
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                diag = analysis["diag"]

                if analysis["faces_found"] == 0:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": diag["msg"],
                        "progress": session["frames"]
                    })
                    continue

                # Handle different stages
                if analysis["precision"] == "low":
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": "⚠️ Stay still for 3D alignment...",
                        "progress": session["frames"]
                    })
                    continue

                # Progress Logic
                success, msg = await asyncio.wait_for(
                    asyncio.to_thread(register_face_to_aws, image_bytes, session["name"]),
                    timeout=10.0
                )
                
                if success:
                    session["frames"] += 1
                    if session["frames"] == 4: session["stage"] = "LEFT"
                    elif session["frames"] == 8: session["stage"] = "RIGHT"
                    
                    await websocket.send_json({
                        "type": "registration_status",
                        "message": f"Captured Stage {session['stage']} ({session['frames']}/12)",
                        "progress": session["frames"]
                    })
                else:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": f"⚠️ AWS Reject: {msg}",
                        "progress": session["frames"]
                    })
                continue

            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                # Push diagnostics even in live view
                msg = analysis["diag"]["msg"] if analysis["faces_found"] == 0 else "✅ System Active"
                
                await websocket.send_json({
                    "type": "ready", 
                    "faces": [], # Add boxes if needed later
                    "debug": msg
                })

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
