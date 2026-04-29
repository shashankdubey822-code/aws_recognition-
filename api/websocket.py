import json
import base64
import time
import asyncio
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from services.face_detector import detect_faces_ultra, extract_embedding_512
from services.attendance import mark_attendance

# LOCAL DB for 512-dim vectors (Centroid Mode)
IDENTITY_DATABASE = {} # { "Name": np.array([512_dims]) }

registration_sessions = {}

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "start_registration":
                name = payload.get("name")
                registration_sessions[websocket] = {
                    "name": name, 
                    "embeddings": [], 
                    "target_count": 200 # CAPTURE 200 IMAGES AS REQUESTED
                }
                await websocket.send_json({"type": "registration_status", "message": f"Stay still. Capturing 200 neural frames...", "progress": 0})
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if len(session["embeddings"]) >= 200: continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # 1. Detect and Extract Image
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                if analysis["faces_found"] == 0:
                    await websocket.send_json({"type": "registration_waiting", "message": "⚠️ Face lost. Stay in frame.", "progress": int((len(session["embeddings"])/200)*100)})
                    continue

                # 2. Extract 512-dim Vector (VERY FAST locally)
                vector = await asyncio.to_thread(extract_embedding_512, analysis["raw_img"])
                
                if vector is not None:
                    session["embeddings"].append(vector)
                    count = len(session["embeddings"])
                    progress = int((count / 200) * 100)
                    
                    if count % 10 == 0: # Update UI every 10 frames for smoothness
                        await websocket.send_json({
                            "type": "registration_status", 
                            "message": f"Generating 512-dim Signature: {progress}%", 
                            "progress": progress
                        })
                    
                    if count >= 200:
                        # 3. Calculate Centroid (Mean of all 200 vectors)
                        centroid = np.mean(session["embeddings"], axis=0)
                        IDENTITY_DATABASE[session["name"]] = centroid
                        await websocket.send_json({
                            "type": "registration_success", 
                            "message": f"✅ {session['name']} profile BAKED using 200 frames."
                        })
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                # Live Recognition using Cosine Similarity against the local 512-dim DB
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] > 0:
                    live_vector = await asyncio.to_thread(extract_embedding_512, analysis["raw_img"])
                    
                    best_match = "Unknown"
                    best_score = 0
                    
                    if live_vector is not None:
                        # Compare against all identities in local DB
                        for name, master_vector in IDENTITY_DATABASE.items():
                            # Cosine Similarity = (A . B) / (||A|| * ||B||)
                            dot_product = np.dot(live_vector, master_vector)
                            norm_a = np.linalg.norm(live_vector)
                            norm_b = np.linalg.norm(master_vector)
                            similarity = (dot_product / (norm_a * norm_b)) * 100
                            
                            if similarity > best_score and similarity > 75:
                                best_score = round(similarity, 1)
                                best_match = name
                    
                    if best_match != "Unknown":
                        mark_attendance(best_match)
                        await websocket.send_json({"type": "attendance", "name": best_match, "time": "Just Now"})

                    b = analysis["box"]
                    client_faces = [{
                        "name": best_match, "score": best_score, "status": "match" if best_match != "Unknown" else "unknown",
                        "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}
                    }]
                    await websocket.send_json({"type": "ready", "faces": client_faces, "debug": f"Match: {best_match} ({best_score}%)"})
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": "🔍 Searching..."})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
