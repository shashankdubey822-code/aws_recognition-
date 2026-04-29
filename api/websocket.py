import json
import base64
import time
import asyncio
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_ultra

registration_sessions = {}
last_aws_call = {}

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_aws_call[websocket] = 0

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "start_registration":
                name = payload.get("name")
                registration_sessions[websocket] = {
                    "name": name, 
                    "frames": 0, 
                    "coverage": [], # List of (yaw, pitch) tuples already captured
                    "last_capture_time": 0
                }
                await websocket.send_json({"type": "registration_status", "message": "Start moving your head slowly...", "progress": 0})
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if session["frames"] >= 15: continue # Hard cap of 15 high-quality unique angles

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] == 0:
                    await websocket.send_json({"type": "registration_waiting", "message": analysis["diag"]["msg"], "progress": int((session["frames"]/15)*100)})
                    continue

                # --- FLUID POSE LOGIC ---
                yaw = analysis["pose"]["yaw"]
                # Check if this angle is "New Enough" (at least 8 degrees different from all previous)
                is_new_angle = True
                for prev_yaw in session["coverage"]:
                    if abs(yaw - prev_yaw) < 8:
                        is_new_angle = False
                        break
                
                now = time.time()
                # Throttling to 1 capture every 400ms to allow AWS processing
                if is_new_angle and (now - session["last_capture_time"] > 0.4):
                    success, msg = await asyncio.to_thread(register_face_to_aws, image_bytes, session["name"])
                    if success:
                        session["frames"] += 1
                        session["coverage"].append(yaw)
                        session["last_capture_time"] = now
                        progress_pct = int((session["frames"] / 15) * 100)
                        
                        await websocket.send_json({
                            "type": "registration_status", 
                            "message": f"Mapping Neural Grid: {progress_pct}%", 
                            "progress": progress_pct
                        })
                    else:
                        await websocket.send_json({"type": "registration_waiting", "message": f"Quality Check: {msg}", "progress": int((session["frames"]/15)*100)})
                else:
                    # Not a new angle, just update progress but tell user to move
                    await websocket.send_json({
                        "type": "registration_waiting", 
                        "message": "Keep rotating your head slowly...", 
                        "progress": int((session["frames"]/15)*100)
                    })
                continue

            if payload.get("type") == "finish_registration":
                if websocket in registration_sessions:
                    name = registration_sessions[websocket]["name"]
                    await websocket.send_json({"type": "registration_success", "message": f"✅ 360° Profile secured for {name}!"})
                    del registration_sessions[websocket]
                continue

            # Live Attendance Loop
            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                if analysis["faces_found"] > 0:
                    now = time.time()
                    if now - last_aws_call.get(websocket, 0) > 0.8:
                        last_aws_call[websocket] = now
                        report = await asyncio.to_thread(search_face_on_aws, image_bytes)
                        client_faces = []
                        if report:
                            for face in report:
                                if face["status"] == "match":
                                    mark_attendance(face["name"])
                                    await websocket.send_json({"type": "attendance", "name": face["name"], "time": "Just Now"})
                                b = analysis["box"]
                                client_faces.append({
                                    "name": face["name"], "score": face["score"], "status": face["status"],
                                    "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                                    "crop": f"data:image/jpeg;base64,{encoded_data}"
                                })
                            await websocket.send_json({"type": "ready", "faces": client_faces, "debug": "✅ System Active"})
                        else:
                            b = analysis["box"]
                            await websocket.send_json({
                                "type": "ready", "faces": [{"name": "Unknown", "score": 0, "status": "unknown", "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}}],
                                "debug": "🎥 Unknown person"
                            })
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": analysis["diag"]["msg"]})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
