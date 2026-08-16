import time
import os
import json
import base64
import asyncio
from fastapi import WebSocket

from services.aws_client import search_face_on_aws, register_face_to_aws
from services.attendance import mark_attendance, parse_identity
from services.face_detector import detect_faces_crowd
from core.config import MIN_FACE_AREA
from core.state import connected_devices
from core.timezone_utils import get_time_str, get_compact_timestamp_str

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
        client_ip = payload.get("ip", "127.0.0.1")
        current_time_str = payload.get("timestamp") or get_time_str()

        # -------------------------------------------------------------
        # 1. PERSIST & BROADCAST RAW UNCROPPED FRAME
        # -------------------------------------------------------------
        os.makedirs("static/raw_frames", exist_ok=True)
        raw_filename = f"raw_{dev_id}_{get_compact_timestamp_str()}_{int(time.time()*1000)%10000}.jpg"
        raw_filepath = os.path.join("static/raw_frames", raw_filename)
        
        try:
            with open(raw_filepath, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            print(f"⚠️ Error saving raw frame: {e}")

        raw_frame_url = f"/static/raw_frames/{raw_filename}"
        raw_record = {
            "url": raw_frame_url,
            "timestamp": current_time_str,
            "ip": client_ip,
            "device_id": dev_id,
            "device_name": dev_name
        }

        # Update connected device state in memory
        if dev_id in connected_devices:
            if "raw_frames" not in connected_devices[dev_id]:
                connected_devices[dev_id]["raw_frames"] = []
            connected_devices[dev_id]["raw_frames"].insert(0, raw_record)
            if len(connected_devices[dev_id]["raw_frames"]) > 30:
                connected_devices[dev_id]["raw_frames"] = connected_devices[dev_id]["raw_frames"][:30]
            
            connected_devices[dev_id]["total_frames"] = (connected_devices[dev_id].get("total_frames", 0)) + 1
            connected_devices[dev_id]["last_seen"] = current_time_str
            connected_devices[dev_id]["status"] = "active"

        # Broadcast new raw frame directly to dashboards
        await self.broadcast_event({
            "type": "new_raw_frame",
            "device_id": dev_id,
            "frame": raw_record
        })

        # -------------------------------------------------------------
        # 2. BROADCAST STAGE: LOCAL AI FACE CROPPING
        # -------------------------------------------------------------
        await self.broadcast_event({
            "type": "device_stage_update",
            "device_id": dev_id,
            "stage": "CROPPING",
            "message": "Local AI Model Extracting Faces..."
        })

        # 3. Detect and crop faces locally using Mediapipe crowd detector
        all_faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
        
        valid_faces = []
        for face in all_faces:
            area = face["box"]["w"] * face["box"]["h"]
            if area >= MIN_FACE_AREA:
                valid_faces.append(face)

        print(f"[EDGE AI] 🔍 Processed frame #{connected_devices.get(dev_id, {}).get('total_frames', 1)} from {dev_name} ({dev_id}): Found {len(valid_faces)} valid faces (Total raw detections: {len(all_faces)})")

        if not valid_faces:
            await self.broadcast_event({
                "type": "device_stage_update",
                "device_id": dev_id,
                "stage": "IDLE",
                "message": "Frame Processed (0 Faces in View)"
            })
            # Also update device overview numbers
            await self.broadcast_event({
                "type": "devices_update",
                "devices": list(connected_devices.values())
            })
            return

        # -------------------------------------------------------------
        # 4. CREATE FIFO CROPPED QUEUE ITEMS
        # -------------------------------------------------------------
        queue_items = []
        search_tasks = []
        
        for idx, vf in enumerate(valid_faces):
            crop_b64 = "data:image/jpeg;base64," + base64.b64encode(vf["bytes"]).decode('utf-8')
            q_id = f"q_{int(time.time()*1000)}_{idx}"

            q_item = {
                "id": q_id,
                "time": current_time_str,
                "crop": crop_b64,
                "status": "scanning",
                "name": "Scanning Face...",
                "roll_number": "...",
                "score": 0.0,
                "result": "🔄 Enqueued in FIFO Pipeline — Dispatched to AWS Rekognition..."
            }
            queue_items.append(q_item)
            search_tasks.append((idx, q_item, vf["bytes"]))

        # Immediate broadcast of enqueued crops into the FIFO drawer
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

        # -------------------------------------------------------------
        # 5. DISPATCH TO AWS REKOGNITION IN BACKGROUND THREADS
        # -------------------------------------------------------------
        for idx, q_item, face_bytes in search_tasks:
            match_res = await asyncio.to_thread(search_face_on_aws, face_bytes)
            
            if dev_id in connected_devices and "cropped_queue" in connected_devices[dev_id]:
                if match_res and match_res.get("match"):
                    identity_str = match_res.get("identity", "Unknown")
                    score = match_res.get("score", 95.0)
                    roll_no, display_name = parse_identity(identity_str)

                    if display_name and display_name != "Unknown":
                        q_item["status"] = "match"
                        q_item["name"] = display_name
                        q_item["roll_number"] = roll_no
                        q_item["score"] = score
                        q_item["result"] = f"✅ AWS MATCH APPROVED ({score}%) — Vector Matched"

                        # Mark session attendance
                        marked, s_time = mark_attendance(
                            identity_str=identity_str,
                            face_bytes=face_bytes,
                            device_id=dev_name or dev_id
                        )

                        if marked:
                            # Save attendee verified thumbnail
                            os.makedirs("static/attendees", exist_ok=True)
                            photo_path = f"static/attendees/attendee_{roll_no}_{get_compact_timestamp_str()}.jpg"
                            try:
                                with open(photo_path, "wb") as pf:
                                    pf.write(face_bytes)
                            except Exception:
                                photo_path = ""

                            student_entry = {
                                "name": display_name,
                                "roll_number": roll_no,
                                "time": s_time or current_time_str,
                                "photo": f"/{photo_path}" if photo_path else ""
                            }
                            
                            if "verified_students" not in connected_devices[dev_id]:
                                connected_devices[dev_id]["verified_students"] = []
                            
                            if not any(s.get("name") == display_name for s in connected_devices[dev_id]["verified_students"]):
                                connected_devices[dev_id]["verified_students"].insert(0, student_entry)

                            # Broadcast attendance confirmation to all UI subscribers
                            await self.broadcast_event({
                                "type": "attendance",
                                "name": display_name,
                                "roll_number": roll_no,
                                "time": s_time or current_time_str,
                                "device_id": dev_name or dev_id,
                                "photo": f"/{photo_path}" if photo_path else ""
                            })
                            print(f"[EDGE AI] 🎓 Attendance verified: {display_name} (Roll: {roll_no}) at {s_time or current_time_str} IST via {dev_name}")
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
        if dev_id in connected_devices:
            await self.broadcast_event({
                "type": "aws_queue_update",
                "device_id": dev_id,
                "queue": connected_devices[dev_id].get("cropped_queue", [])
            })
            await self.broadcast_event({
                "type": "devices_update",
                "devices": list(connected_devices.values())
            })

        await self.broadcast_event({
            "type": "device_stage_update",
            "device_id": dev_id,
            "stage": "IDLE",
            "message": f"Cycle Complete ({len(valid_faces)} Faces Processed)"
        })
