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
                
                # HARD BOUNDARY: Stop backend if 12 frames reached
                if session["frames"] >= 12:
                    continue

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

                # ROBUST POSE LOGIC: Use relative head position
                # yaw is now approximated from Nose vs Face center
                yaw = analysis["pose"]["yaw"]
                stage = session["stage"]
                is_compliant = False
                instruction = ""

                if stage == "CENTER":
                    if -18 < yaw < 18: is_compliant = True
                    else: instruction = "Look directly at the center dot"
                elif stage == "LEFT":
                    if yaw > 20: is_compliant = True # Leniency boost
                    else: instruction = "Turn your head LEFT"
                elif stage == "RIGHT":
                    if yaw < -20: is_compliant = True
                    else: instruction = "Turn your head RIGHT"

                if not is_compliant:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": f"⏳ {instruction}",
                        "progress": session["frames"]
                    })
                    continue

                # Register Frame
                success, msg = await asyncio.to_thread(register_face_to_aws, image_bytes, session["name"])
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

            if payload.get("type") == "finish_registration":
                if websocket in registration_sessions:
                    name = registration_sessions[websocket]["name"]
                    await websocket.send_json({
                        "type": "registration_success",
                        "message": f"✅ Profile secured for {name}!"
                    })
                    del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                msg = analysis["diag"]["msg"] if analysis["faces_found"] == 0 else "✅ System Active"
                
                await websocket.send_json({
                    "type": "ready", 
                    "faces": [], 
                    "debug": msg
                })

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
