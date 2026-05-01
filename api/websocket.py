import json
import base64
import time
import asyncio
import sqlite3
import os
import random
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

os.makedirs("static/intruders", exist_ok=True)
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_crowd
from services.liveness_engine import score_liveness, warmup
from core.state import DB_PATH
from core.config import MIN_FACE_AREA
from core.tracker import CentroidTracker

# Pre-warm MiniFASNet model into RAM on startup
try:
    warmup()
except Exception as e:
    print(f"[LIVENESS] Warmup skipped: {e}")

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
                    import random
                    name = payload.get("name")
                    # Generate a random 3-step sequence for AGI active liveness
                    seq = random.sample(["LEFT", "RIGHT", "UP", "DOWN"], 3)
                    registration_sessions[websocket] = {"name": name, "frames": 0, "sequence": seq}
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

                    face = faces[0]
                    
                    # --- ENVIRONMENTAL AUTO-COACHING ---
                    brightness = face.get("brightness", 100)
                    blur = face.get("blur", 100)
                    
                    if brightness < 40:
                        await websocket.send_json({"type": "registration_waiting", "message": "Lighting too dark. Move to a brighter area.", "progress": int((session["frames"]/20)*100)})
                        continue
                    if blur < 50:
                        await websocket.send_json({"type": "registration_waiting", "message": "Camera out of focus. Please hold still.", "progress": int((session["frames"]/20)*100)})
                        continue
                        
                    # --- ACTIVE LIVENESS (RANDOMIZED SIMON SAYS) ---
                    nose_x, nose_y = None, None
                    if "landmarks" in face and len(face["landmarks"]) > 2:
                        nose_x = face["landmarks"][2]["x"]
                        nose_y = face["landmarks"][2]["y"]
                        
                    if nose_x is not None and nose_y is not None:
                        bbox = face["box"]
                        nose_rel_x = (nose_x - bbox["x"]) / (bbox["w"] + 1e-6)
                        nose_rel_y = (nose_y - bbox["y"]) / (bbox["h"] + 1e-6)
                        frames = session["frames"]
                        
                        if frames < 5:
                            if not (0.35 < nose_rel_x < 0.65 and 0.35 < nose_rel_y < 0.65):
                                await websocket.send_json({"type": "registration_waiting", "message": "Maintain Center Lock. Look straight ahead.", "progress": int((frames/20)*100)})
                                continue
                        else:
                            step = 0
                            if 5 <= frames < 10: step = 0
                            elif 10 <= frames < 15: step = 1
                            elif 15 <= frames < 20: step = 2
                            
                            current_challenge = session.get("sequence", ["LEFT", "RIGHT", "UP"])[step]
                            
                            if current_challenge == "LEFT":
                                if nose_rel_x < 0.55: 
                                    await websocket.send_json({"type": "registration_waiting", "message": "Turn head LEFT to continue.", "progress": int((frames/20)*100)})
                                    continue
                            elif current_challenge == "RIGHT":
                                if nose_rel_x > 0.45:
                                    await websocket.send_json({"type": "registration_waiting", "message": "Turn head RIGHT to continue.", "progress": int((frames/20)*100)})
                                    continue
                            elif current_challenge == "UP":
                                if nose_rel_y > 0.45: # Nose moves UP -> Y decreases
                                    await websocket.send_json({"type": "registration_waiting", "message": "Tilt head UP to continue.", "progress": int((frames/20)*100)})
                                    continue
                            elif current_challenge == "DOWN":
                                if nose_rel_y < 0.55: # Nose moves DOWN -> Y increases
                                    await websocket.send_json({"type": "registration_waiting", "message": "Tilt head DOWN to continue.", "progress": int((frames/20)*100)})
                                    continue

                    # --- IDENTITY GUARD ---
                    if session["frames"] == 0:
                        search_results = await asyncio.to_thread(search_face_on_aws, face["bytes"])
                        if search_results and any(res["status"] == "match" for res in search_results):
                            match_name = next(res["name"] for res in search_results if res["status"] == "match")
                            await websocket.send_json({
                                "type": "registration_error", 
                                "message": f"Identity Conflict: This person is already registered as '{match_name.replace('_', ' ')}'."
                            })
                            del registration_sessions[websocket]
                            continue

                    success, msg = await asyncio.to_thread(register_face_to_aws, face["bytes"], session["name"])
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

                    # Update tracker geometry (centroid matching)
                    tracked_objects = tracker.update(valid_faces)

                    # --- MINIFASNET LIVENESS SCORING (async, per face) ---
                    # Score each visible face and inject into tracker
                    liveness_tasks = []
                    liveness_ids   = []
                    for object_id, obj in tracked_objects.items():
                        # Skip faces already confirmed by challenge or fully verified
                        if obj["challenge_state"] in ("verified_real", "active"):
                            continue
                        # Find the matching face crop bytes
                        for vf in valid_faces:
                            if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                                liveness_tasks.append(asyncio.to_thread(score_liveness, vf["bytes"]))
                                liveness_ids.append(object_id)
                                break

                    if liveness_tasks:
                        liveness_scores = await asyncio.gather(*liveness_tasks)
                        for obj_id, ls in zip(liveness_ids, liveness_scores):
                            tracker.inject_liveness_score(obj_id, ls)

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
                        # ALLOW challenge-active faces through — they are being verified interactively
                        if obj["liveness"] == "spoof" and obj["challenge_state"] not in ("active", "verified_real"):
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
                                    
                                    # --- FEDERATED LEARNING (DYNAMIC PROFILES) ---
                                    if res["score"] > 98.0 and not tracker.objects[obj_id].get("federated_updated"):
                                        tracker.objects[obj_id]["federated_updated"] = True
                                        asyncio.create_task(asyncio.to_thread(register_face_to_aws, vf["bytes"], res["name"]))
                                        print(f"[FEDERATED LEARNING] Updated AWS neural profile for {res['name']} (Score: {res['score']})")

                                    # Mark Attendance
                                    mark_attendance(res["name"])
                                    await websocket.send_json({"type": "attendance", "name": res["name"], "time": "Now"})
                                else:
                                    tracker.objects[obj_id]["aws_status"] = "failed"

                    # --- CHALLENGE-RESPONSE ENGINE ---
                    # Triggers ONLY when a face has been in red-box (spoof) state for sustained frames
                    SPOOF_STREAK_THRESHOLD = 20  # ~2 seconds of continuous spoof detection
                    for object_id, obj in tracked_objects.items():
                        c_state = obj.get("challenge_state")

                        # TRIGGER: Red-box face hit the streak threshold → initiate challenge
                        if obj["spoof_streak"] >= SPOOF_STREAK_THRESHOLD and c_state is None:
                            instruction = random.choice(["LEFT", "RIGHT", "UP", "DOWN"])
                            # Capture current nose as baseline
                            baseline = (0.5, 0.5)
                            hist = obj.get("landmarks_history", [])
                            if hist:
                                last = hist[-1]
                                baseline = (last[1], 0.5)  # nose_x from tuple (ratio, nose_x)

                            tracker.objects[object_id]["challenge_state"] = "active"
                            tracker.objects[object_id]["challenge_instruction"] = instruction
                            tracker.objects[object_id]["challenge_baseline"] = baseline
                            tracker.objects[object_id]["challenge_compliance_frames"] = 0
                            tracker.objects[object_id]["challenge_start_time"] = time.time()
                            print(f"[CHALLENGE] 🎯 Issuing challenge to face {object_id}: {instruction}")
                            await websocket.send_json({
                                "type": "challenge",
                                "face_id": object_id,
                                "instruction": instruction
                            })

                        # PASSED: Tracker math confirmed real human → notify frontend, re-open AWS gate
                        elif c_state == "verified_real":
                            tracker.objects[object_id]["challenge_state"] = None
                            await websocket.send_json({
                                "type": "challenge_passed",
                                "face_id": object_id,
                                "message": "✅ Liveness Confirmed — Identity Verification Proceeding"
                            })

                        # TIMEOUT: Challenge active but 15 seconds elapsed → spoof confirmed
                        elif c_state == "active":
                            start_t = obj.get("challenge_start_time", time.time())
                            if time.time() - start_t > 15:
                                tracker.objects[object_id]["challenge_state"] = "verified_spoof"
                                tracker.objects[object_id]["liveness"] = "spoof"
                                tracker.objects[object_id]["aws_status"] = "spoof"
                                tracker.objects[object_id]["name"] = "SPOOF CONFIRMED"
                                print(f"[CHALLENGE] ❌ Face {object_id} FAILED challenge — timeout")
                                await websocket.send_json({
                                    "type": "challenge_failed",
                                    "face_id": object_id,
                                    "message": "❌ Challenge Failed — Spoof Confirmed"
                                })



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
