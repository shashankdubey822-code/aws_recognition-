import json
import base64
import time
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_crowd

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
                registration_sessions[websocket] = {"name": name, "frames": 0}
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if session["frames"] >= 10: continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                
                if not faces:
                    await websocket.send_json({"type": "registration_waiting", "message": "🔍 No face detected", "progress": int((session["frames"]/10)*100)})
                    continue

                success, msg = await asyncio.to_thread(register_face_to_aws, faces[0]["bytes"], session["name"])
                if success:
                    session["frames"] += 1
                    progress = int((session["frames"]/10)*100)
                    await websocket.send_json({"type": "registration_status", "message": f"Angle {session['frames']}/10 Secured ✓", "progress": progress})
                    if session["frames"] >= 10:
                        await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} profile indexed."})
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "finish_registration":
                if websocket in registration_sessions:
                    name = registration_sessions[websocket]["name"]
                    await websocket.send_json({"type": "registration_success", "message": f"✅ {name} profile secured."})
                    del registration_sessions[websocket]
                continue

            # --- ROBUST NON-BLOCKING ATTENDANCE LOOP ---
            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # 1. Detect all faces locally (INSTANT)
                faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                
                client_faces = []
                debug_msg = "🔍 Monitoring..."
                
                if faces:
                    now = time.time()
                    # 2. Check if we should perform AWS Search (Throttled)
                    if now - last_aws_call.get(websocket, 0) > 1.2:
                        last_aws_call[websocket] = now
                        
                        # Parallel Fan-Out to AWS
                        search_tasks = [asyncio.to_thread(search_face_on_aws, f["bytes"]) for f in faces]
                        aws_results = await asyncio.gather(*search_tasks)
                        
                        for i, face_report in enumerate(aws_results):
                            b = faces[i]["box"]
                            name = "Unknown"
                            status = "unknown"
                            score = 0
                            
                            if face_report and len(face_report) > 0:
                                res = face_report[0]
                                name = res["name"]
                                status = res["status"]
                                score = res["score"]
                                
                                if status == "match":
                                    mark_attendance(name)
                                    # Send immediate attendance ping for UI
                                    await websocket.send_json({"type": "attendance", "name": name, "time": "Now"})
                            
                            client_faces.append({
                                "name": name, "score": score, "status": status,
                                "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                                "crop": f"data:image/jpeg;base64,{base64.b64encode(faces[i]['bytes']).decode()}"
                            })
                        debug_msg = f"✅ Crowd detected: {len(faces)} people"
                    else:
                        # 3. AWS Cooldown - Just return boxes for smooth tracking
                        for f in faces:
                            b = f["box"]
                            client_faces.append({
                                "name": "Scanning...", "score": 0, "status": "verifying",
                                "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}
                            })
                        debug_msg = "🎥 Local tracking active..."

                # CRITICAL: Always send 'ready' to release the frontend lock
                await websocket.send_json({
                    "type": "ready",
                    "faces": client_faces,
                    "debug": debug_msg
                })

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
