import cv2
import time
import base64
import random
import asyncio
from datetime import datetime
from fastapi import WebSocket

from services.detector import detect_and_crop_faces
from services.liveness_engine import check_liveness_minifasnet
from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance, parse_identity
from core.state import connected_devices

class TrackingController:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        from services.tracker import GlobalTracker
        self.tracker = GlobalTracker()
        self.last_intruder_time = 0

    async def process_frame(self, payload: dict):
        # Decode base64
        encoded_data = payload["image"].split(',')[1]
        nparr = cv2.imdecode(cv2.np.frombuffer(base64.b64decode(encoded_data), cv2.np.uint8), cv2.IMREAD_COLOR)
        
        dev_id = payload.get("device_id", "edge_device")
        dev_name = payload.get("device_name", "Edge Node")

        # 1. Detection via YOLOv8 Face
        valid_faces, raw_faces = detect_and_crop_faces(nparr)
        
        # 2. Update Global Centroid / Feature Tracker
        tracked_objects = self.tracker.update(valid_faces, nparr)
        
        search_tasks = []
        search_object_ids = []
        queue_items = []
        
        # 3. Liveness Analysis & Search Pipeline
        for idx, (object_id, obj) in enumerate(tracked_objects.items()):
            # Run MiniFASNet ONNX Inference
            crop_img = obj.get("crop")
            if crop_img is not None and crop_img.size > 0:
                is_real, conf = check_liveness_minifasnet(crop_img)
                if not is_real:
                    obj["spoof_streak"] += 1
                    obj["liveness"] = "spoof"
                else:
                    obj["spoof_streak"] = max(0, obj["spoof_streak"] - 1)
                    obj["liveness"] = "real"

            # Intruder Capture (Unknown entity seen for >30 consecutive frames)
            if obj["liveness"] == "real" and obj["aws_status"] == "unknown" and obj["frames_active"] > 30:
                now = time.time()
                if now - self.last_intruder_time > 10:
                    self.last_intruder_time = now
                    for vf in valid_faces:
                        try:
                            timestamp = int(now)
                            with open(f"static/intruders/intruder_{timestamp}.jpg", "wb") as f:
                                f.write(vf["bytes"])
                            await self.websocket.send_json({
                                "type": "intruder_alert",
                                "message": "UNREGISTERED ENTITY DETECTED",
                                "image": f"/static/intruders/intruder_{timestamp}.jpg"
                            })
                        except Exception as e:
                            print(f"Failed to save intruder: {e}")
                        break

            # Liveness check before AWS
            if obj["liveness"] == "spoof" and obj["challenge_state"] not in ("active", "verified_real"):
                obj["aws_status"] = "spoof"
                obj["name"] = "SPOOF DETECTED"
                
                # Build spoof queue item
                for vf in valid_faces:
                    if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                        crop_b64 = "data:image/jpeg;base64," + base64.b64encode(vf["bytes"]).decode('utf-8')
                        q_item = {
                            "id": f"q_{int(time.time()*1000)}_{idx}",
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "crop": crop_b64,
                            "status": "spoof",
                            "name": "SPOOF ATTACK",
                            "roll_number": "N/A",
                            "score": 0.0,
                            "result": "🛑 LIVENESS FAILED — Anti-Spoof Shield Triggered"
                        }
                        queue_items.append(q_item)
                        break
                continue
                
            # If face is still scanning and we haven't asked AWS 3 times
            if obj["aws_status"] == "unknown" and obj["aws_calls"] < 3 and obj["liveness"] == "real":
                for vf in valid_faces:
                    if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                        search_tasks.append(asyncio.to_thread(search_face_on_aws, vf["bytes"]))
                        search_object_ids.append(object_id)
                        obj["aws_calls"] += 1
                        
                        crop_b64 = "data:image/jpeg;base64," + base64.b64encode(vf["bytes"]).decode('utf-8')
                        q_item = {
                            "id": f"q_{int(time.time()*1000)}_{idx}",
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "crop": crop_b64,
                            "status": "scanning",
                            "name": "Scanning...",
                            "roll_number": "...",
                            "score": 0.0,
                            "result": "🔄 Enqueued in FIFO Pipeline — Contacting AWS Rekognition..."
                        }
                        queue_items.append(q_item)
                        break
        
        # Run AWS calls in parallel
        if search_tasks:
            aws_results = await asyncio.gather(*search_tasks)
            for i, face_report in enumerate(aws_results):
                obj_id = search_object_ids[i]
                if face_report and len(face_report) > 0:
                    res = face_report[0]
                    if res["status"] == "match":
                        raw_id = res["name"]
                        display_name, roll_no = parse_identity(raw_id)
                        
                        self.tracker.objects[obj_id]["name"] = display_name
                        self.tracker.objects[obj_id]["roll_number"] = roll_no
                        self.tracker.objects[obj_id]["aws_status"] = "match"
                        self.tracker.objects[obj_id]["score"] = res["score"]
                        
                        matched_bytes = None
                        for vf in valid_faces:
                            if vf["box"]["x"] == self.tracker.objects[obj_id]["box"]["x"] and vf["box"]["y"] == self.tracker.objects[obj_id]["box"]["y"]:
                                matched_bytes = vf["bytes"]
                                break

                        # Federated Learning update
                        if res["score"] > 98.0 and not self.tracker.objects[obj_id].get("federated_updated") and matched_bytes:
                            self.tracker.objects[obj_id]["federated_updated"] = True
                            asyncio.create_task(asyncio.to_thread(register_face_to_aws, matched_bytes, raw_id))
                            print(f"[FEDERATED LEARNING] Updated AWS neural profile for {display_name} (Score: {res['score']})")

                        # Mark Attendance with photo and device_id mapping
                        status, s_name, s_roll, s_time = mark_attendance(raw_id, matched_bytes, device_id=dev_id)
                        if status in ("success", "already_marked"):
                            await self.websocket.send_json({
                                "type": "attendance", 
                                "name": display_name, 
                                "roll_number": roll_no,
                                "time": s_time or "Now",
                                "device_id": dev_id
                            })
                            
                        # Update queue item result
                        if i < len(queue_items):
                            queue_items[i]["status"] = "match"
                            queue_items[i]["name"] = display_name
                            queue_items[i]["roll_number"] = roll_no
                            queue_items[i]["score"] = round(res["score"], 1)
                            queue_items[i]["result"] = f"✅ AWS MATCH APPROVED: {display_name} (Roll: {roll_no}) [Confidence: {res['score']:.1f}%]"
                    else:
                        self.tracker.objects[obj_id]["aws_status"] = "failed"
                        if i < len(queue_items):
                            queue_items[i]["status"] = "no_match"
                            queue_items[i]["name"] = "Unknown Entity"
                            queue_items[i]["roll_number"] = "N/A"
                            queue_items[i]["result"] = "❌ NO MATCH IN AWS DATABASE — Identity Unregistered"
                else:
                    self.tracker.objects[obj_id]["aws_status"] = "failed"
                    if i < len(queue_items):
                        queue_items[i]["status"] = "no_match"
                        queue_items[i]["name"] = "Unknown Entity"
                        queue_items[i]["roll_number"] = "N/A"
                        queue_items[i]["result"] = "❌ NO MATCH IN AWS DATABASE — Identity Unregistered"

        # Update per-device FIFO cropped queue
        if queue_items and dev_id in connected_devices:
            if "cropped_queue" not in connected_devices[dev_id]:
                connected_devices[dev_id]["cropped_queue"] = []
            for qi in queue_items:
                connected_devices[dev_id]["cropped_queue"].insert(0, qi)
            if len(connected_devices[dev_id]["cropped_queue"]) > 25:
                connected_devices[dev_id]["cropped_queue"] = connected_devices[dev_id]["cropped_queue"][:25]

            # Broadcast FIFO Queue update to connected UI clients
            await self.websocket.send_json({
                "type": "aws_queue_update",
                "device_id": dev_id,
                "queue": connected_devices[dev_id]["cropped_queue"]
            })

        # --- CHALLENGE-RESPONSE ENGINE ---
        SPOOF_STREAK_THRESHOLD = 20
        for object_id, obj in tracked_objects.items():
            c_state = obj.get("challenge_state")

            if obj["spoof_streak"] >= SPOOF_STREAK_THRESHOLD and c_state is None:
                instruction = random.choice(["LEFT", "RIGHT", "UP", "DOWN"])
                baseline = (0.5, 0.5)
                hist = obj.get("landmarks_history", [])
                if hist:
                    last = hist[-1]
                    baseline = (last[1], 0.5)

                self.tracker.objects[object_id]["challenge_state"] = "active"
                self.tracker.objects[object_id]["challenge_instruction"] = instruction
                self.tracker.objects[object_id]["challenge_start_time"] = time.time()
                self.tracker.objects[object_id]["challenge_baseline"] = baseline

                await self.websocket.send_json({
                    "type": "challenge_issued",
                    "face_id": object_id,
                    "instruction": instruction,
                    "box": obj["box"],
                    "timeout": 5.0
                })

        # 4. Construct Response JSON
        client_faces = []
        for object_id, obj in tracked_objects.items():
            display_name = obj["name"]
            status = obj["aws_status"]
            if obj["liveness"] == "spoof" and obj["challenge_state"] != "verified_real":
                display_name = "SPOOF DETECTED"
                status = "spoof"
            elif status == "match":
                status = "match"
            elif status == "failed":
                display_name = "Unknown Entity"

            crop_b64 = None
            if obj.get("crop") is not None and obj["crop"].size > 0:
                _, buffer = cv2.imencode('.jpg', obj["crop"])
                crop_b64 = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')

            client_faces.append({
                "id": object_id,
                "box": obj["box"],
                "name": display_name,
                "roll_number": obj.get("roll_number", "N/A"),
                "raw_name": obj["name"],
                "status": status,
                "liveness": obj["liveness"],
                "score": obj.get("score", 0),
                "crop": crop_b64
            })
            
        await self.websocket.send_json({"type": "ready", "faces": client_faces})
