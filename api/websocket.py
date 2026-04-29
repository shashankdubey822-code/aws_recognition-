import json
import base64
import time
import asyncio
import sqlite3
from fastapi import WebSocket, WebSocketDisconnect
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_crowd
from core.state import DB_PATH, consensus_votes, last_known_positions

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
                        # Save to local persistent DB
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute("INSERT OR IGNORE INTO registered_faces (name) VALUES (?)", (session["name"],))
                        conn.commit(); conn.close()
                        await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} profile persistent."})
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
                
                client_faces = []
                now = time.time()

                if faces:
                    search_tasks = []
                    faces_to_search_indices = []

                    for i, face in enumerate(faces):
                        b = face["box"]
                        # --- LOGIC 1: DEDUPLICATION (Movement Check) ---
                        # We use a simple Face ID based on spatial proximity (x, y)
                        face_id = f"{round(b['x'], 1)}_{round(b['y'], 1)}"
                        
                        moved = True
                        if face_id in last_known_positions:
                            old_pos = last_known_positions[face_id]
                            # If moved less than 5%, it's the same person in the same spot
                            if abs(b['x'] - old_pos['x']) < 0.05 and abs(b['y'] - old_pos['y']) < 0.05:
                                moved = False
                        
                        if moved or (now - last_aws_call.get(websocket, 0) > 3.0):
                            search_tasks.append(asyncio.to_thread(search_face_on_aws, face["bytes"]))
                            faces_to_search_indices.append(i)
                            last_known_positions[face_id] = {"x": b['x'], "y": b['y'], "name": "Scanning..."}

                    if search_tasks and (now - last_aws_call.get(websocket, 0) > 1.2):
                        last_aws_call[websocket] = now
                        aws_results = await asyncio.gather(*search_tasks)
                        
                        for i, face_report in enumerate(aws_results):
                            original_index = faces_to_search_indices[i]
                            b = faces[original_index]["box"]
                            face_id = f"{round(b['x'], 1)}_{round(b['y'], 1)}"
                            
                            name = "Unknown"
                            if face_report and len(face_report) > 0:
                                res = face_report[0]
                                name = res["name"] if res["status"] == "match" else "Unknown"

                            # --- LOGIC 2: CONSENSUS (The 3-Vote Rule) ---
                            if face_id not in consensus_votes: consensus_votes[face_id] = []
                            consensus_votes[face_id].append(name)
                            if len(consensus_votes[face_id]) > 3: consensus_votes[face_id].pop(0)

                            # Only confirm if 3 most recent votes are the same
                            final_name = "Unknown"
                            if len(consensus_votes[face_id]) >= 3 and len(set(consensus_votes[face_id])) == 1:
                                final_name = consensus_votes[face_id][0]
                                if final_name != "Unknown":
                                    mark_attendance(final_name)
                                    await websocket.send_json({"type": "attendance", "name": final_name, "time": "Now"})

                            last_known_positions[face_id]["name"] = final_name
                            
                    # Prepare UI Response
                    for i, face in enumerate(faces):
                        b = face["box"]
                        face_id = f"{round(b['x'], 1)}_{round(b['y'], 1)}"
                        cached_name = last_known_positions.get(face_id, {}).get("name", "Scanning...")
                        
                        client_faces.append({
                            "name": cached_name,
                            "status": "match" if cached_name != "Unknown" and cached_name != "Scanning..." else "unknown",
                            "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)},
                            "crop": f"data:image/jpeg;base64,{base64.b64encode(face['bytes']).decode()}"
                        })

                await websocket.send_json({"type": "ready", "faces": client_faces, "debug": f"Tracking {len(faces)} people | Local Persistence Active"})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
