import json
import base64
import time
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance
from services.face_detector import detect_faces_local

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
                registration_sessions[websocket] = {"name": name, "frames": 0, "validated_faces": []}
                await websocket.send_json({
                    "type": "registration_status",
                    "message": f"Initializing scanner for {name}",
                    "progress": 0
                })
                continue

            if payload.get("type") == "register_frame":
                if websocket not in registration_sessions:
                    continue

                now = time.time()
                if now - last_aws_call[websocket] < 0.3:
                    await websocket.send_json({
                        "type": "registration_waiting",
                        "message": "Processing...",
                        "progress": registration_sessions[websocket].get("frames", 0) * 4
                    })
                    continue
                last_aws_call[websocket] = now

                try:
                    encoded_data = payload["image"].split(',')[1]
                    image_bytes = base64.b64decode(encoded_data)

                    local_detection = await asyncio.to_thread(detect_faces_local, image_bytes)

                    if not local_detection.get("should_send_to_aws", False):
                        await websocket.send_json({
                            "type": "registration_waiting",
                            "message": "⚠️ No face detected - position yourself in camera",
                            "progress": registration_sessions[websocket].get("frames", 0) * 4
                        })
                        continue

                    name = registration_sessions[websocket]["name"]
                    
                    if registration_sessions[websocket].get("frames", 0) == 0:
                        duplicate_check = await asyncio.wait_for(
                            asyncio.to_thread(search_face_on_aws, image_bytes),
                            timeout=8.0
                        )
                        if duplicate_check and len(duplicate_check) > 0:
                            match = duplicate_check[0]
                            existing_name = match.get("name", "Unknown")
                            similarity = match.get("score", 0)
                            
                            if existing_name != "Unknown":
                                if existing_name.lower() == name.lower():
                                    await websocket.send_json({
                                        "type": "registration_error",
                                        "message": f"⚠️ '{name}' is already registered in the system."
                                    })
                                else:
                                    await websocket.send_json({
                                        "type": "registration_error",
                                        "message": f"⚠️ This face matches '{existing_name}' ({similarity}% similarity). Use different face."
                                    })
                                if websocket in registration_sessions:
                                    del registration_sessions[websocket]
                                continue

                    success, msg = await asyncio.wait_for(
                        asyncio.to_thread(register_face_to_aws, image_bytes, name),
                        timeout=10.0
                    )

                    if success:
                        registration_sessions[websocket]["frames"] += 1
                        registration_sessions[websocket]["validated_faces"].append(image_bytes)
                        count = registration_sessions[websocket]["frames"]
                        progress = count * 4

                        await websocket.send_json({
                            "type": "registration_status",
                            "message": f"Captured angle {count}/3 ✓",
                            "progress": progress
                        })
                    else:
                        await websocket.send_json({
                            "type": "registration_waiting",
                            "message": f"Quality check failed: {msg}. Try again...",
                            "progress": registration_sessions[websocket].get("frames", 0) * 4
                        })
                except asyncio.TimeoutError:
                    await websocket.send_json({
                        "type": "registration_error",
                        "message": "AWS timeout. Check your connection and try again."
                    })
                    if websocket in registration_sessions:
                        del registration_sessions[websocket]
                except Exception as e:
                    print(f"Registration frame error: {e}")
                    await websocket.send_json({
                        "type": "registration_error",
                        "message": f"Error: {str(e)[:60]}"
                    })
                    if websocket in registration_sessions:
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "finish_registration":
                if websocket not in registration_sessions:
                    continue

                try:
                    session_data = registration_sessions[websocket]
                    name = session_data["name"]

                    await websocket.send_json({
                        "type": "registration_success",
                        "message": f"✅ '{name}' successfully registered!"
                    })
                except Exception as e:
                    print(f"Finish registration error: {e}")
                    await websocket.send_json({
                        "type": "registration_success",
                        "message": f"✅ Registration completed."
                    })
                finally:
                    if websocket in registration_sessions:
                        del registration_sessions[websocket]
                continue

            if payload.get("type") == "frame":
                if websocket in registration_sessions:
                    continue

                encoded_data = payload["image"].split(',')[1]
                image_bytes = base64.b64decode(encoded_data)

                local_detection = await asyncio.to_thread(detect_faces_local, image_bytes)

                if not local_detection.get("should_send_to_aws", False):
                    await websocket.send_json({
                        "type": "ready",
                        "debug": f"🎥 Capturing... No face detected",
                        "faces": []
                    })
                    continue

                now = time.time()
                if now - last_aws_call.get(websocket, 0) < 0.5:
                    num_faces = local_detection.get("faces_found", 0)
                    await websocket.send_json({
                        "type": "ready",
                        "debug": f"🎥 Scanning... {num_faces} face(s)",
                        "faces": []
                    })
                    continue
                last_aws_call[websocket] = now

                try:
                    report = await asyncio.wait_for(
                        asyncio.to_thread(search_face_on_aws, image_bytes),
                        timeout=8.0
                    )
                except asyncio.TimeoutError:
                    await websocket.send_json({
                        "type": "ready",
                        "debug": "⏱️ AWS timeout - retrying...",
                        "faces": []
                    })
                    continue
                except Exception as e:
                    print(f"AWS search error: {e}")
                    await websocket.send_json({
                        "type": "ready",
                        "debug": f"❌ Error: {str(e)[:40]}",
                        "faces": []
                    })
                    continue

                results_summary = []
                client_faces = []
                yolo_faces = local_detection.get("faces_found", 0)

                if report:
                    for face in report:
                        name = face["name"]
                        score = face["score"]
                        status = face["status"]

                        aws_b = face["aws_box"]
                        pixel_box = {
                            "x": int(aws_b["Left"] * 640),
                            "y": int(aws_b["Top"] * 480),
                            "w": int(aws_b["Width"] * 640),
                            "h": int(aws_b["Height"] * 480)
                        }

                        client_faces.append({
                            "name": name,
                            "score": score,
                            "status": status,
                            "box": pixel_box,
                            "crop": f"data:image/jpeg;base64,{encoded_data}"
                        })

                        if status == "match":
                            status_db, time_str = await asyncio.to_thread(mark_attendance, name)
                            results_summary.append(f"✅ {name} ({score}%)")

                            await websocket.send_json({
                                "type": "attendance",
                                "name": name,
                                "time": time_str or "Now",
                                "status": "success"
                            })
                        else:
                            results_summary.append(f"⚠️ {name} ({score}%)")
                    debug_msg = " | ".join(results_summary)
                else:
                    debug_msg = f"🎥 Face detected ({yolo_faces}) but not in database"

                await websocket.send_json({
                    "type": "ready",
                    "debug": debug_msg,
                    "faces": client_faces
                })

    except WebSocketDisconnect:
        if websocket in registration_sessions:
            del registration_sessions[websocket]
        if websocket in last_aws_call:
            del last_aws_call[websocket]
    except Exception as e:
        print(f"WebSocket Error: {e}")