import json
import base64
import time
import asyncio
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
                registration_sessions[websocket] = {"name": name, "frames": 0, "stage": "CENTER"}
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if session["frames"] >= 12: continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] == 0:
                    await websocket.send_json({"type": "registration_waiting", "message": analysis["diag"]["msg"], "progress": session["frames"]})
                    continue

                yaw = analysis["pose"]["yaw"] if "pose" in analysis else 0
                is_compliant = False
                instruction = ""

                if session["stage"] == "CENTER":
                    if -18 < yaw < 18: is_compliant = True
                    else: instruction = "Look directly at the center dot"
                elif session["stage"] == "LEFT":
                    if yaw > 20: is_compliant = True
                    else: instruction = "Turn your head LEFT"
                elif session["stage"] == "RIGHT":
                    if yaw < -20: is_compliant = True
                    else: instruction = "Turn your head RIGHT"

                if not is_compliant:
                    await websocket.send_json({"type": "registration_waiting", "message": f"⏳ {instruction}", "progress": session["frames"]})
                    continue

                success, msg = await asyncio.to_thread(register_face_to_aws, image_bytes, session["name"])
                if success:
                    session["frames"] += 1
                    if session["frames"] == 4: session["stage"] = "LEFT"
                    elif session["frames"] == 8: session["stage"] = "RIGHT"
                    await websocket.send_json({"type": "registration_status", "message": f"Captured {session['stage']} ({session['frames']}/12)", "progress": session["frames"]})
                else:
                    await websocket.send_json({"type": "registration_waiting", "message": f"⚠️ AWS Reject: {msg}", "progress": session["frames"]})
                continue

            if payload.get("type") == "finish_registration":
                if websocket in registration_sessions:
                    name = registration_sessions[websocket]["name"]
                    await websocket.send_json({"type": "registration_success", "message": f"✅ Profile secured for {name}!"})
                    del registration_sessions[websocket]
                continue

            # --- RESTORED CORE ATTENDANCE LOOP ---
            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # 1. Local Detection
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] > 0:
                    now = time.time()
                    # 2. Throttled AWS Recognition
                    if now - last_aws_call.get(websocket, 0) > 0.8:
                        last_aws_call[websocket] = now
                        report = await asyncio.to_thread(search_face_on_aws, image_bytes)
                        
                        client_faces = []
                        if report:
                            for face in report:
                                name = face["name"]
                                status = face["status"]
                                score = face["score"]
                                
                                # 3. Mark Attendance if matched
                                if status == "match":
                                    mark_status, time_str = mark_attendance(name)
                                    await websocket.send_json({"type": "attendance", "name": name, "time": time_str or "Just Now"})
                                
                                # 4. Prepare box for UI
                                b = analysis["box"] # Use the box from local detector
                                client_faces.append({
                                    "name": name, "score": score, "status": status,
                                    "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                                    "crop": f"data:image/jpeg;base64,{encoded_data}" # For AI Eye
                                })
                            
                            await websocket.send_json({"type": "ready", "faces": client_faces, "debug": f"Precision: {analysis['precision']}"})
                        else:
                            # Face detected but AWS returned nothing (Unknown)
                            b = analysis["box"]
                            await websocket.send_json({
                                "type": "ready", 
                                "faces": [{"name": "Unknown", "score": 0, "status": "unknown", "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}}],
                                "debug": "🎥 Unknown person detected"
                            })
                    else:
                        # Throttling - don't send faces yet to save bandwidth
                        await websocket.send_json({"type": "ready", "faces": [], "debug": "🎥 Scanning..."})
                else:
                    # No face at all
                    await websocket.send_json({"type": "ready", "faces": [], "debug": analysis["diag"]["msg"]})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
