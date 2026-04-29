import json
import base64
import time
import asyncio
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from services.face_detector import detect_faces_ultra, get_embedding_batch
from services.attendance import mark_attendance

IDENTITY_DATABASE = {} 
registration_sessions = {}

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "start_registration":
                name = payload.get("name")
                registration_sessions[websocket] = {"name": name, "raw_faces": [], "is_baking": False}
                await websocket.send_json({"type": "registration_status", "message": "INITIALIZING NEURAL LINK...", "progress": 0})
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions: continue
                session = registration_sessions[websocket]
                if session["is_baking"] or len(session["raw_faces"]) >= 200: continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                
                # Fast local detection
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] > 0:
                    session["raw_faces"].append(analysis["face_img"])
                    count = len(session["raw_faces"])
                    progress = int((count / 200) * 100)
                    
                    # ACKNOWLEDGMENT: Send back for every single neuron
                    await websocket.send_json({
                        "type": "registration_status", 
                        "message": f"NEURON SYNCED: [{count}/200]", 
                        "progress": progress
                    })
                    
                    if count >= 200:
                        session["is_baking"] = True
                        await websocket.send_json({"type": "registration_status", "message": "BAKING 512-DIM SIGNATURE...", "progress": 100})
                        
                        # Process 200 images in one background thread
                        centroid = await asyncio.to_thread(get_embedding_batch, session["raw_faces"])
                        
                        if centroid is not None:
                            IDENTITY_DATABASE[session["name"]] = centroid
                            await websocket.send_json({"type": "registration_success", "message": f"✅ {session['name']} Neural Profile Secured!"})
                        else:
                            await websocket.send_json({"type": "registration_error", "message": "❌ Neural Synthesis failed. Bad lighting?"})
                        
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                # Regular recognition logic (Throttled for stability)
                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)
                analysis = await asyncio.to_thread(detect_faces_ultra, image_bytes)
                
                if analysis["faces_found"] > 0:
                    # Single frame check for live view
                    live_vector = await asyncio.to_thread(get_embedding_batch, [analysis["face_img"]])
                    
                    best_match = "Unknown"
                    best_score = 0
                    if live_vector is not None:
                        for name, master in IDENTITY_DATABASE.items():
                            similarity = (np.dot(live_vector, master) / (np.linalg.norm(live_vector) * np.linalg.norm(master))) * 100
                            if similarity > best_score and similarity > 75:
                                best_score = round(similarity, 1); best_match = name
                    
                    if best_match != "Unknown": mark_attendance(best_match)
                    
                    b = analysis["box"]
                    await websocket.send_json({
                        "type": "ready", 
                        "faces": [{"name": best_match, "score": best_score, "box": {"x": int(b["x"]*640), "y": int(b["y"]*480), "w": int(b["w"]*640), "h": int(b["h"]*480)}}],
                        "debug": f"Active: {best_match}"
                    })
                else:
                    await websocket.send_json({"type": "ready", "faces": [], "debug": "🔍 Searching..."})

    except WebSocketDisconnect:
        if websocket in registration_sessions: del registration_sessions[websocket]
    except Exception as e:
        print(f"WS Error: {e}")
