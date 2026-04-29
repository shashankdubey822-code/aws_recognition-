import json
import base64
import time
import asyncio
import sqlite3
import os
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

os.makedirs("static/intruders", exist_ok=True)
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_crowd
from core.state import DB_PATH
from core.config import MIN_FACE_AREA
from core.tracker import CentroidTracker

registration_sessions = {}
# Global tracker instance per websocket (or global if needed, but per-websocket is safer for multiple cameras)
# We will use a dictionary to store tracker per websocket
trackers = {}

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    trackers[websocket] = CentroidTracker(max_disappeared=15, max_distance=0.15)
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                payload = json.loads(data)

                if payload.get("type") == "start_registration":
                    name = payload.get("name")
                    registration_sessions[websocket] = {"name": name, "frames": 0}
                    continue

                if payload.get("type") == "register_frame":
                    if websocket not in registration_sessions: continue
                    session = registration_sessions[websocket]
                    if session["frames"] >= 20: continue # Upgraded to 20 frames for 3D mapping

                    encoded_data = payload["image"].split(',')[1]
                    image_bytes = base64.b64decode(encoded_data)
                    faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                    
                    if not faces:
                        await websocket.send_json({"type": "registration_waiting", "message": "🔍 No face detected", "progress": int((session["frames"]/20)*100)})
                        continue

                    # --- IDENTITY GUARD ---
                    if session["frames"] == 0:
                        search_results = await asyncio.to_thread(search_face_on_aws, faces[0]["bytes"])
                        if search_results and any(res["status"] == "match" for res in search_results):
                            match_name = next(res["name"] for res in search_results if res["status"] == "match")
                            await websocket.send_json({
                                "type": "registration_error", 
                                "message": f"Identity Conflict: This person is already registered as '{match_name.replace('_', ' ')}'."
                            })
                            del registration_sessions[websocket]
                            continue

                    success, msg = await asyncio.to_thread(register_face_to_aws, faces[0]["bytes"], session["name"])
                    if success:
                        session["frames"] += 1
                        progress = int((session["frames"]/20)*100)
                        await websocket.send_json({"type": "registration_status", "message": f"Angle {session['frames']}/20 Secured ✓", "progress": progress})
                        if session["frames"] >= 20:
                            conn = sqlite3.connect(DB_PATH)
                            conn.execute("INSERT OR IGNORE INTO registered_faces (name) VALUES (?)", (session["name"],))
                            conn.commit(); conn.close()
                            await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} profile persistent."})
                            del registration_sessions[websocket]
                    continue

                if payload.get("type") == "frame":
                    encoded_data = payload["image"].split(',')[1]
                    image_bytes = base64.b64decode(encoded_data)
                    
                    # Detect faces locally
                    all_faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                    
                    # Filter out small faces (posters/backgrounds)
                    valid_faces = []
                    for face in all_faces:
                        area = face["box"]["w"] * face["box"]["h"]
                        if area >= MIN_FACE_AREA:
                            valid_faces.append(face)

                    tracker = trackers[websocket]
                    
                    # Update tracker
                    tracked_objects = tracker.update(valid_faces)
                    
                    client_faces = []
                    search_tasks = []
                    search_object_ids = []
                    
                    for object_id, obj in tracked_objects.items():
                        # Intruder Alert Capture
                        if obj["aws_status"] == "failed" and obj["aws_calls"] >= 3 and not obj.get("intruder_alerted"):
                            obj["intruder_alerted"] = True
                            for vf in valid_faces:
                                if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                                    timestamp = int(time.time())
                                    filepath = f"static/intruders/intruder_{timestamp}.jpg"
                                    try:
                                        with open(filepath, "wb") as f:
                                            f.write(vf["bytes"])
                                        await websocket.send_json({
                                            "type": "intruder_alert",
                                            "message": "UNREGISTERED ENTITY DETECTED",
                                            "image": f"/static/intruders/intruder_{timestamp}.jpg"
                                        })
                                    except Exception as e:
                                        print(f"Failed to save intruder: {e}")
                                    break

                        # Liveness check before AWS
                        if obj["liveness"] == "spoof":
                            obj["aws_status"] = "spoof"
                            obj["name"] = "SPOOF DETECTED"
                            continue # Block AWS ping!
                            
                        # If face is still scanning and we haven't asked AWS 3 times
                        if obj["aws_status"] == "unknown" and obj["aws_calls"] < 3 and obj["liveness"] == "real":
                            for vf in valid_faces:
                                if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                                    search_tasks.append(asyncio.to_thread(search_face_on_aws, vf["bytes"]))
                                    search_object_ids.append(object_id)
                                    obj["aws_calls"] += 1
                                    break
                    
                    # Run AWS calls in parallel
                    if search_tasks:
                        aws_results = await asyncio.gather(*search_tasks)
                        for i, face_report in enumerate(aws_results):
                            obj_id = search_object_ids[i]
                            if face_report and len(face_report) > 0:
                                res = face_report[0]
                                if res["status"] == "match":
                                    tracker.objects[obj_id]["name"] = res["name"]
                                    tracker.objects[obj_id]["aws_status"] = "match"
                                    tracker.objects[obj_id]["score"] = res["score"]
                                    
                                    # Mark Attendance
                                    mark_attendance(res["name"])
                                    await websocket.send_json({"type": "attendance", "name": res["name"], "time": "Now"})
                                else:
                                    tracker.objects[obj_id]["aws_status"] = "failed" # AWS says it's unknown

                    # Prepare UI Response
                    for object_id, obj in tracked_objects.items():
                        # We don't send bytes back to UI to save bandwidth, unless requested. 
                        # We will just send the box and status.
                        # We use the valid_faces array to get the crop if needed, but for performance, 
                        # UI can use coordinates to draw boxes locally over the video feed!
                        crop_str = ""
                        for vf in valid_faces:
                            if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                                crop_str = f"data:image/jpeg;base64,{base64.b64encode(vf['bytes']).decode()}"
                                break

                        client_faces.append({
                            "id": object_id,
                            "name": obj["name"],
                            "status": obj["aws_status"] if obj["name"] != "Scanning..." else "verifying",
                            "score": obj["score"],
                            "box": {"x": int(obj["box"]["x"]*640), "y": int(obj["box"]["y"]*480), "w": int(obj["box"]["w"]*640), "h": int(obj["box"]["h"]*480)},
                            "crop": crop_str
                        })

                    await websocket.send_json({
                        "type": "ready", 
                        "faces": client_faces, 
                        "debug": f"Tracking {len(tracked_objects)} people"
                    })

            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "close" in str(e).lower():
                    break
                print(f"Frame Error: {e}")
                try: await websocket.send_json({"type": "error", "message": f"Frame Error: {str(e)}"})
                except: pass
            except Exception as e:
                # Catch per-frame exceptions so we don't drop the connection!
                print(f"Frame Error: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": f"Frame Processing Error: {str(e)}"})
                except:
                    pass

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
        if websocket in trackers: del trackers[websocket]
    except Exception as e:
        print(f"WS Fatal Error: {e}")
