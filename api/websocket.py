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

            if payload.get("type") == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack"})
                continue

            if payload.get("type") == "start_registration":
                name = payload.get("name")
                registration_sessions[websocket] = {
                    "name": name, 
                    "frames": 0, 
                    "stage": "CENTER", # CENTER, LEFT, RIGHT
                    "validated_faces": []
                }
                await websocket.send_json({
                    "type": "registration_status",
                    "message": "Initializing 3D Neural Mapping...",
                    "progress": 0
                })
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions:
                    continue

                session = registration_sessions[websocket]
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)

                # 🧠 VIBECODER ACTION: Ultra-Accurate Multi-Agent Check
                # Runs pose estimation, liveness, and face detection in parallel
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)

                if analysis.get("faces_found", 0) == 0:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": "⚠️ Face lost! Stay in frame.",
                        "progress": session["frames"]
                    })
                    continue

                pose = analysis["pose"]
                yaw = pose["yaw"]
                stage = session["stage"]

                # 🏗️ RULE: GEOMETRIC COMPLIANCE
                is_compliant = False
                instruction = ""

                if stage == "CENTER":
                    if -15 < yaw < 15:
                        is_compliant = True
                    else:
                        instruction = "Look directly at the center dot"
                elif stage == "LEFT":
                    if yaw > 25:
                        is_compliant = True
                    else:
                        instruction = "Turn your head LEFT (Follow the dot)"
                elif stage == "RIGHT":
                    if yaw < -25:
                        is_compliant = True
                    else:
                        instruction = "Turn your head RIGHT (Follow the dot)"

                if not is_compliant:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": f"⏳ {instruction}",
                        "progress": session["frames"]
                    })
                    continue

                # 🧬 RULE: IDENTITY LOCKING (FRAME 0 ANCHOR)
                # On Frame 0, we verify they aren't already registered
                if session["frames"] == 0:
                    duplicate_check = await asyncio.to_thread(search_face_on_aws, image_bytes)
                    if duplicate_check and any(f["status"] == "match" for f in duplicate_check):
                        await websocket.send_json({
                            "type": "registration_error",
                            "message": "❌ Identity already registered in system."
                        })
                        del registration_sessions[websocket]
                        continue

                # ✅ PASS: Capture frame to AWS
                success, msg = await asyncio.to_thread(register_face_to_aws, image_bytes, session["name"])
                
                if success:
                    session["frames"] += 1
                    # Progress Stages: 0-3 Center, 4-7 Left, 8-11 Right
                    if session["frames"] == 4: session["stage"] = "LEFT"
                    elif session["frames"] == 8: session["stage"] = "RIGHT"

                    await websocket.send_json({
                        "type": "registration_status",
                        "message": f"Neural Link Stabilized: Stage {session['stage']} ({session['frames']}/12)",
                        "progress": session["frames"]
                    })
                else:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": f"Quality Check: {msg}",
                        "progress": session["frames"]
                    })
                continue

            if payload.get("type") == "finish_registration":
                if websocket in registration_sessions:
                    name = registration_sessions[websocket]["name"]
                    await websocket.send_json({
                        "type": "registration_success",
                        "message": f"✅ {name} profile secured."
                    })
                    del registration_sessions[websocket]
                continue

            # Standard attendance logic remains the same
            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # Use ultra detector even for live view for smoother metrics
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis.get("faces_found", 0) > 0:
                    # Throttle AWS calls
                    now = time.time()
                    if now - last_aws_call.get(websocket, 0) > 0.6:
                        last_aws_call[websocket] = now
                        report = await asyncio.to_thread(search_face_on_aws, image_bytes)
                        
                        client_faces = []
                        if report:
                            for face in report:
                                if face["status"] == "match":
                                    mark_attendance(face["name"])
                                    await websocket.send_json({"type": "attendance", "name": face["name"], "time": "Just Now"})
                                
                                # Convert normalized AWS box to pixels
                                b = face["aws_box"]
                                client_faces.append({
                                    "name": face["name"],
                                    "score": face["score"],
                                    "status": face["status"],
                                    "box": {"x": int(b["Left"]*640), "y": int(b["Top"]*480), "w": int(b["Width"]*640), "h": int(b["Height"]*480)}
                                })
                        
                        await websocket.send_json({"type": "ready", "faces": client_faces, "debug": f"Yaw: {analysis['pose']['yaw']:.1f}°"})
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": "🎥 Searching..."})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
