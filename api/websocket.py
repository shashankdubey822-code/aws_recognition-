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

            # Registration logic (Single face only for profile security)
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

                # Use the first face for registration
                success, msg = await asyncio.to_thread(register_face_to_aws, faces[0]["bytes"], session["name"])
                if success:
                    session["frames"] += 1
                    progress = int((session["frames"]/10)*100)
                    await websocket.send_json({"type": "registration_status", "message": f"Angle {session['frames']}/10 Secured ✓", "progress": progress})
                    if session["frames"] >= 10:
                        await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} 3D profile indexed."})
                        del registration_sessions[websocket]
                continue

            # --- PARALLEL CROWD RECOGNITION ---
            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # 1. Detect all faces locally (FAST)
                faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                
                if faces:
                    now = time.time()
                    if now - last_aws_call.get(websocket, 0) > 1.2:
                        last_aws_call[websocket] = now
                        
                        # 2. Parallel "Fan-Out" to AWS
                        # We create a list of tasks for each face crop found
                        search_tasks = [asyncio.to_thread(search_face_on_aws, f["bytes"]) for f in faces]
                        results = await asyncio.gather(*search_tasks)
                        
                        client_faces = []
                        for i, face_report in enumerate(results):
                            # The original box from local detector
                            b = faces[i]["box"]
                            
                            if face_report and len(face_report) > 0:
                                res = face_report[0]
                                name = res["name"]
                                status = res["status"]
                                score = res["score"]
                                
                                if status == "match":
                                    mark_attendance(name)
                                    await websocket.send_json({"type": "attendance", "name": name, "time": "Now"})
                                
                                client_faces.append({
                                    "name": name, "score": score, "status": status,
                                    "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                                    "crop": f"data:image/jpeg;base64,{base64.b64encode(faces[i]['bytes']).decode()}"
                                })
                            else:
                                # This specific face was not matched
                                client_faces.append({
                                    "name": "Unknown", "score": 0, "status": "unknown",
                                    "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                                    "crop": f"data:image/jpeg;base64,{base64.b64encode(faces[i]['bytes']).decode()}"
                                })
                        
                        await websocket.send_json({"type": "ready", "faces": client_faces, "debug": f"Crowd detected: {len(faces)} people"})
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": "🔍 Monitoring..."})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
