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
                    "angles_captured": [], # List of yaw angles captured
                    "target": 10 # 10 HIGH QUALITY ANGLES
                }
                await websocket.send_json({"type": "registration_status", "message": "Rotate your head slowly (10 unique angles)...", "progress": 0})
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if session["frames"] >= session["target"]: continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] == 0:
                    await websocket.send_json({"type": "registration_waiting", "message": "⚠️ Face lost. Stay in frame.", "progress": int((session["frames"]/10)*100)})
                    continue

                # AWS ANGLE LOGIC: Only capture if head has moved > 10 degrees from previous angle
                yaw = analysis["pose"]["yaw"]
                is_new_angle = True
                for prev_yaw in session["angles_captured"]:
                    if abs(yaw - prev_yaw) < 10:
                        is_new_angle = False
                        break
                
                if is_new_angle:
                    # Index to AWS
                    success, msg = await asyncio.to_thread(register_face_to_aws, image_bytes, session["name"])
                    if success:
                        session["frames"] += 1
                        session["angles_captured"].append(yaw)
                        progress = int((session["frames"]/10)*100)
                        await websocket.send_json({
                            "type": "registration_status", 
                            "message": f"Angle {session['frames']}/10 Indexed ✓", 
                            "progress": progress
                        })
                    
                    if session["frames"] >= 10:
                        await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} registered on AWS with 10 angles."})
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                # LIVE AWS RECOGNITION
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] > 0:
                    now = time.time()
                    if now - last_aws_call.get(websocket, 0) > 1.0: # AWS throttle (1 sec)
                        last_aws_call[websocket] = now
                        report = await asyncio.to_thread(search_face_on_aws, image_bytes)
                        
                        client_faces = []
                        if report:
                            for face in report:
                                if face["status"] == "match":
                                    mark_attendance(face["name"])
                                    await websocket.send_json({"type": "attendance", "name": face["name"], "time": "Now"})
                                
                                b = analysis["box"]
                                client_faces.append({
                                    "name": face["name"], "score": face["score"], "status": face["status"],
                                    "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}
                                })
                            await websocket.send_json({"type": "ready", "faces": client_faces, "debug": "☁️ AWS Recon Active"})
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": "🔍 Searching..."})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
