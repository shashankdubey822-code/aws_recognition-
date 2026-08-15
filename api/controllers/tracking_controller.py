import time
import json
import base64
import asyncio
from datetime import datetime
from fastapi import WebSocket

from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance, parse_identity
from services.face_detector import detect_faces_crowd
from core.config import MIN_FACE_AREA
from core.state import connected_devices

class TrackingController:
    def __init__(self, websocket: WebSocket, broadcast_func=None):
        self.websocket = websocket
        self.broadcast_func = broadcast_func or websocket.send_json

    async def broadcast_event(self, event_dict: dict):
        """Dispatches telemetry event to ALL connected dashboard browsers."""
        try:
            await self.broadcast_func(event_dict)
        except Exception as e:
            try:
                await self.websocket.send_json(event_dict)
            except Exception:
                pass

    async def process_frame(self, payload: dict):
        encoded_data = payload["image"].split(',')[1]
        image_bytes = base64.b64decode(encoded_data)
        
        dev_id = payload.get("device_id", "edge_device")
        dev_name = payload.get("device_name", "Edge Node")

        # 1. Broadcast Stage: Local AI Face Cropping Active
        await self.broadcast_event({
            "type": "device_stage_update",
            "device_id": dev_id,
            "stage": "CROPPING",
            "message": "Local AI Model Extracting Faces..."
        })

        # 2. Detect and crop faces locally using Mediapipe crowd detector
        all_faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
        
        valid_faces = []
        for face in all_faces:
            area = face["box"]["w"] * face["box"]["h"]
            if area >= MIN_FACE_AREA:
                valid_faces.append(face)

        print(f"[EDGE AI] 🔍 Processed frame from {dev_name} ({dev_id}): Found {len(valid_faces)} valid faces (Total raw detections: {len(all_faces)})")

        if not valid_faces:
            await self.broadcast_event({
                "type": "device_stage_update",
                "device_id": dev_id,
                "stage": "IDLE",
                "message": "Frame Processed (0 Faces in View)"
            })
            return

        # 3. Create FIFO Cropped Queue Items (Direct to AWS — NO SPOOF BLOCKING)
        queue_items = []
        search_tasks = []
        
        for idx, vf in enumerate(valid_faces):
            crop_b64 = "data:image/jpeg;base64," + base64.b64encode(vf["bytes"]).decode('utf-8')
            q_id = f"q_{int(time.time()*1000)}_{idx}"

            q_item = {
                "id": q_id,
                "time": datetime.now().strftime("%H:%M:%S"),
                "crop": crop_b64,
                "status": "scanning",
                "name": "Scanning Face...",
                "roll_number": "...",
                "score": 0.0,
                "result": "🔄 Enqueued in FIFO Pipeline — Dispatched to AWS Rekognition..."
            }
            queue_items.append(q_item)
            search_tasks.append((idx, q_item, vf["bytes"]))

        # 4. Immediate broadcast of enqueued crops into the FIFO drawer
        if dev_id in connected_devices:
            if "cropped_queue" not in connected_devices[dev_id]:
                connected_devices[dev_id]["cropped_queue"] = []
            for qi in queue_items:
                connected_devices[dev_id]["cropped_queue"].insert(0, qi)
            if len(connected_devices[dev_id]["cropped_queue"]) > 30:
                connected_devices[dev_id]["cropped_queue"] = connected_devices[dev_id]["cropped_queue"][:30]

            await self.broadcast_event({
                "type": "device_stage_update",
                "device_id": dev_id,
                "stage": "AWS_MATCHING",
                "message": f"Contacting AWS Cloud AI ({len(search_tasks)} faces)..."
            })

            await self.broadcast_event({
                "type": "aws_queue_update",
                "device_id": dev_id,
                "queue": connected_devices[dev_id]["cropped_queue"]
            })

        # 5. Run AWS Rekognition searches in parallel
        if search_tasks:
            aws_futures = [asyncio.to_thread(search_face_on_aws, task[2]) for task in search_tasks]
            aws_results = await asyncio.gather(*aws_futures)

            for i, face_report in enumerate(aws_results):
                idx, q_item, face_bytes = search_tasks[i]
                
                if face_report and len(face_report) > 0:
                    res = face_report[0]
                    if res["status"] == "match":
                        raw_id = res["name"]
                        display_name, roll_no = parse_identity(raw_id)
                        confidence = round(res["score"], 1)

                        q_item["status"] = "match"
                        q_item["name"] = display_name
                        q_item["roll_number"] = roll_no
                        q_item["score"] = confidence
                        q_item["result"] = f"✅ AWS MATCH APPROVED: {display_name} (Roll: {roll_no}) [Confidence: {confidence}%]"

                        # Mark Attendance with photo & device_id
                        status, s_name, s_roll, s_time = mark_attendance(raw_id, face_bytes, device_id=dev_id)
                        if status in ("success", "already_marked"):
                            await self.broadcast_event({
                                "type": "attendance", 
                                "name": display_name, 
                                "roll_number": roll_no,
                                "time": s_time or "Now",
                                "device_id": dev_id
                            })
                            print(f"[EDGE AI] 🎓 Attendance marked: {display_name} (Roll: {roll_no}) via {dev_id}")
                    else:
                        q_item["status"] = "no_match"
                        q_item["name"] = "Unknown Entity"
                        q_item["roll_number"] = "N/A"
                        q_item["result"] = "❌ NO MATCH IN AWS DATABASE — Identity Unregistered"
                else:
                    q_item["status"] = "no_match"
                    q_item["name"] = "Unknown Entity"
                    q_item["roll_number"] = "N/A"
                    q_item["result"] = "❌ NO MATCH IN AWS DATABASE — Identity Unregistered"

        # 6. Broadcast final updated FIFO queue & stage complete
        if dev_id in connected_devices and "cropped_queue" in connected_devices[dev_id]:
            await self.broadcast_event({
                "type": "aws_queue_update",
                "device_id": dev_id,
                "queue": connected_devices[dev_id]["cropped_queue"]
            })

        await self.broadcast_event({
            "type": "device_stage_update",
            "device_id": dev_id,
            "stage": "IDLE",
            "message": f"Cycle Complete ({len(valid_faces)} Faces Processed)"
        })
