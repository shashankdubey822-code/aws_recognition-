import time
import json
import base64
import asyncio
import random
from datetime import datetime
from fastapi import WebSocket

from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance, parse_identity
from services.face_detector import detect_faces_crowd
from services.liveness_engine import score_liveness
from core.config import MIN_FACE_AREA
from core.tracker import CentroidTracker
from core.state import connected_devices

class TrackingController:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.tracker = CentroidTracker(max_disappeared=15, max_distance=0.15)

    async def process_frame(self, payload: dict):
        encoded_data = payload["image"].split(',')[1]
        image_bytes = base64.b64decode(encoded_data)
        
        dev_id = payload.get("device_id", "edge_device")
        dev_name = payload.get("device_name", "Edge Node")

        # 1. Detect faces locally using Mediapipe crowd detector
        all_faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
        
        # Filter out small faces (posters/backgrounds)
        valid_faces = []
        for face in all_faces:
            area = face["box"]["w"] * face["box"]["h"]
            if area >= MIN_FACE_AREA:
                valid_faces.append(face)

        # 2. Update Centroid Tracker
        tracked_objects = self.tracker.update(valid_faces)

        search_tasks = []
        search_object_ids = []
        queue_items = []

        # 3. Liveness Analysis & Search Pipeline
        for idx, (object_id, obj) in enumerate(tracked_objects.items()):
            # Liveness Scoring
            for vf in valid_faces:
                if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                    liveness_score, liveness_reason = score_liveness(
                        obj["landmarks_history"],
                        obj["brightness_history"],
                        obj["blur_history"],
                        fft_val=vf.get("fft_max_hf", 0.0)
                    )
                    obj["liveness_score"] = liveness_score

                    if liveness_score < 0.40:
                        obj["spoof_streak"] += 1
                        if obj["spoof_streak"] >= 3:
                            obj["liveness"] = "spoof"
                    else:
                        obj["spoof_streak"] = max(0, obj["spoof_streak"] - 1)
                        if obj["spoof_streak"] == 0:
                            obj["liveness"] = "real"
                    break

            # Intruder Capture
            if obj["liveness"] == "real" and obj["aws_status"] == "unknown" and obj["frames_active"] > 30:
                now = time.time()
                if now - getattr(self, "last_intruder_time", 0) > 10:
                    self.last_intruder_time = now
                    for vf in valid_faces:
                        timestamp = int(time.time())
                        filepath = f"static/intruders/intruder_{timestamp}.jpg"
                        try:
                            with open(filepath, "wb") as f:
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
            if obj["liveness"] == "spoof" and obj.get("challenge_state") not in ("active", "verified_real"):
                obj["aws_status"] = "spoof"
                obj["name"] = "SPOOF DETECTED"

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

                        # Find face image bytes for snapshot and federated update
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
        SPOOF_STREAK_THRESHOLD = 20  # ~2 seconds of continuous spoof detection
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
                self.tracker.objects[object_id]["challenge_baseline"] = baseline
                self.tracker.objects[object_id]["challenge_compliance_frames"] = 0
                self.tracker.objects[object_id]["challenge_start_time"] = time.time()
                print(f"[CHALLENGE] 🎯 Issuing challenge to face {object_id}: {instruction}")
                await self.websocket.send_json({
                    "type": "challenge",
                    "face_id": object_id,
                    "instruction": instruction
                })

            elif c_state == "verified_real":
                self.tracker.objects[object_id]["challenge_state"] = None
                await self.websocket.send_json({
                    "type": "challenge_passed",
                    "face_id": object_id,
                    "message": "✅ Liveness Confirmed — Identity Verification Proceeding"
                })

            elif c_state == "active":
                start_t = obj.get("challenge_start_time", time.time())
                if time.time() - start_t > 15:
                    self.tracker.objects[object_id]["challenge_state"] = "verified_spoof"
                    self.tracker.objects[object_id]["liveness"] = "spoof"
                    self.tracker.objects[object_id]["aws_status"] = "spoof"
                    self.tracker.objects[object_id]["name"] = "SPOOF CONFIRMED"
                    print(f"[CHALLENGE] ❌ Face {object_id} FAILED challenge — timeout")
                    await self.websocket.send_json({
                        "type": "challenge_failed",
                        "face_id": object_id,
                        "message": "❌ Challenge Failed — Spoof Confirmed"
                    })

        # Prepare UI Response
        client_faces = []
        for object_id, obj in tracked_objects.items():
            crop_str = ""
            for vf in valid_faces:
                if vf["box"]["x"] == obj["box"]["x"] and vf["box"]["y"] == obj["box"]["y"]:
                    crop_str = f"data:image/jpeg;base64,{base64.b64encode(vf['bytes']).decode()}"
                    break

            display_title = obj["name"]
            if obj.get("roll_number") and obj["roll_number"] != "N/A" and obj["name"] not in ("Scanning...", "SPOOF DETECTED", "SPOOF CONFIRMED"):
                display_title = f"{obj['name']} ({obj['roll_number']})"

            client_faces.append({
                "id": object_id,
                "name": display_title,
                "raw_name": obj["name"],
                "roll_number": obj.get("roll_number", "N/A"),
                "status": obj["aws_status"] if obj["name"] != "Scanning..." else "verifying",
                "score": obj["score"],
                "box": {
                    "x": int(obj["box"]["x"]*640), 
                    "y": int(obj["box"]["y"]*480), 
                    "w": int(obj["box"]["w"]*640), 
                    "h": int(obj["box"]["h"]*480)
                },
                "crop": crop_str
            })

        await self.websocket.send_json({
            "type": "ready", 
            "faces": client_faces, 
            "debug": f"Tracking {len(tracked_objects)} people"
        })
