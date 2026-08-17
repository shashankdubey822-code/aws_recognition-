import base64
import asyncio
import sqlite3
import random
import re
from fastapi import WebSocket

from services.aws_client import search_face_on_aws, register_face_to_aws
from services.face_detector import detect_faces_crowd
from services.attendance import parse_identity
from core.state import DB_PATH

class RegistrationController:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session = None

    def start_registration(self, payload: dict):
        name = payload.get("name", "").strip()
        roll_number = payload.get("roll_number", "").strip() or "N/A"
        
        # Clean identity key for AWS Rekognition external image ID (only [a-zA-Z0-9_.\-:] allowed by AWS)
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.replace(" ", "_"))
        safe_roll = re.sub(r'[^a-zA-Z0-9_]', '_', roll_number)
        identity_key = f"{safe_roll}__{safe_name}"
        
        seq = random.sample(["LEFT", "RIGHT", "UP", "DOWN"], 3)
        self.session = {
            "name": name,
            "roll_number": roll_number,
            "identity_key": identity_key,
            "frames": 0,
            "sequence": seq,
            "conflict_checked": False
        }

    async def process_frame(self, payload: dict):
        if not self.session:
            return
        if self.session["frames"] >= 20:
            return

        encoded_data = payload["image"].split(',')[1]
        image_bytes = base64.b64decode(encoded_data)
        faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
        
        if not faces:
            await self.websocket.send_json({
                "type": "registration_waiting", 
                "step": "face_detection",
                "message": "🔍 No face detected in frame. Align face in target box.", 
                "progress": int((self.session["frames"]/20)*100)
            })
            return

        face = faces[0]
        
        # Environmental Coaching & Live Telemetry
        brightness = face.get("brightness", 100)
        blur = face.get("blur", 100)
        telemetry = {
            "brightness": round(brightness, 1),
            "blur": round(blur, 1),
            "confidence": round(face.get("confidence", 0.95) * 100, 1)
        }

        if brightness < 40:
            await self.websocket.send_json({
                "type": "registration_waiting", 
                "step": "environmental",
                "message": "⚠️ Lighting too dark. Move to a brighter area.", 
                "progress": int((self.session["frames"]/20)*100),
                "telemetry": telemetry
            })
            return
        if blur < 50:
            await self.websocket.send_json({
                "type": "registration_waiting", 
                "step": "environmental",
                "message": "⚠️ Camera out of focus / motion blur. Please hold still.", 
                "progress": int((self.session["frames"]/20)*100),
                "telemetry": telemetry
            })
            return

        # Active Liveness Pose Check
        nose_x, nose_y = None, None
        if "landmarks" in face and len(face["landmarks"]) > 2:
            nose_x = face["landmarks"][2]["x"]
            nose_y = face["landmarks"][2]["y"]
            
        if nose_x is not None and nose_y is not None:
            bbox = face["box"]
            nose_rel_x = (nose_x - bbox["x"]) / (bbox["w"] + 1e-6)
            nose_rel_y = (nose_y - bbox["y"]) / (bbox["h"] + 1e-6)
            frames = self.session["frames"]
            
            if frames < 5:
                if not (0.35 < nose_rel_x < 0.65 and 0.35 < nose_rel_y < 0.65):
                    await self.websocket.send_json({
                        "type": "registration_waiting", 
                        "step": "pose_liveness",
                        "direction": "CENTER",
                        "message": "🎯 Maintain Center Lock. Look straight ahead.", 
                        "progress": int((frames/20)*100),
                        "telemetry": telemetry
                    })
                    return
            else:
                step = 0
                if 5 <= frames < 10: step = 0
                elif 10 <= frames < 15: step = 1
                elif 15 <= frames < 20: step = 2
                
                current_challenge = self.session.get("sequence", ["LEFT", "RIGHT", "UP"])[step]
                
                if current_challenge == "LEFT":
                    if nose_rel_x < 0.55: 
                        await self.websocket.send_json({
                            "type": "registration_waiting", 
                            "step": "pose_liveness",
                            "direction": "LEFT",
                            "message": "⬅️ Turn head slightly LEFT to capture side profile...", 
                            "progress": int((frames/20)*100),
                            "telemetry": telemetry
                        })
                        return
                elif current_challenge == "RIGHT":
                    if nose_rel_x > 0.45:
                        await self.websocket.send_json({
                            "type": "registration_waiting", 
                            "step": "pose_liveness",
                            "direction": "RIGHT",
                            "message": "➡️ Turn head slightly RIGHT to capture side profile...", 
                            "progress": int((frames/20)*100),
                            "telemetry": telemetry
                        })
                        return
                elif current_challenge == "UP":
                    if nose_rel_y > 0.45:
                        await self.websocket.send_json({
                            "type": "registration_waiting", 
                            "step": "pose_liveness",
                            "direction": "UP",
                            "message": "⬆️ Tilt head slightly UP to capture chin & jaw profile...", 
                            "progress": int((frames/20)*100),
                            "telemetry": telemetry
                        })
                        return
                elif current_challenge == "DOWN":
                    if nose_rel_y < 0.55:
                        await self.websocket.send_json({
                            "type": "registration_waiting", 
                            "step": "pose_liveness",
                            "direction": "DOWN",
                            "message": "⬇️ Tilt head slightly DOWN to complete 3D angle map...", 
                            "progress": int((frames/20)*100),
                            "telemetry": telemetry
                        })
                        return

        # Identity Conflict Guard (First frame check across AWS collection)
        if not self.session.get("conflict_checked", False):
            await self.websocket.send_json({
                "type": "registration_step_update",
                "step": "conflict_check",
                "status": "running",
                "message": "🔍 Scanning AWS Cloud Collection for duplicate enrolment..."
            })
            
            search_res = await asyncio.to_thread(search_face_on_aws, face["bytes"])
            
            if isinstance(search_res, list):
                search_res = search_res[0] if len(search_res) > 0 else {}

            if isinstance(search_res, dict) and search_res.get("match"):
                matched_raw = search_res.get("identity", "Unknown")
                matched_name, matched_roll = parse_identity(matched_raw)
                
                err_text = f"Identity Conflict: Face already registered as '{matched_name}' (Roll No: {matched_roll})."
                await self.websocket.send_json({
                    "type": "registration_error", 
                    "step": "conflict_check",
                    "message": err_text
                })
                self.session = None
                return
            
            self.session["conflict_checked"] = True
            await self.websocket.send_json({
                "type": "registration_step_update",
                "step": "conflict_check",
                "status": "success",
                "message": "✅ Identity clear. No existing record found in cloud."
            })

        # Register Vector Embedding to AWS Rekognition
        success, msg = await asyncio.to_thread(register_face_to_aws, face["bytes"], self.session["identity_key"])
        if success:
            self.session["frames"] += 1
            progress = int((self.session["frames"]/20)*100)
            await self.websocket.send_json({
                "type": "registration_status", 
                "step": "indexing",
                "message": f"Biometric Angle {self.session['frames']}/20 Vector Secured ✓", 
                "angle": self.session["frames"],
                "progress": progress,
                "telemetry": telemetry
            })
            
            if self.session["frames"] >= 20:
                # Save to local SQLite database
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("INSERT OR REPLACE INTO registered_faces (roll_number, name) VALUES (?, ?)", 
                                 (self.session["roll_number"], self.session["name"]))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"⚠️ Local DB Error during registration: {e}")

                await self.websocket.send_json({
                    "type": "registration_success", 
                    "step": "complete",
                    "message": f"✅ Student '{self.session['name']}' [Roll: {self.session['roll_number']}] Registered Successfully in Cloud & Database."
                })
                self.session = None
        else:
            await self.websocket.send_json({
                "type": "registration_waiting",
                "step": "indexing",
                "message": f"AWS indexing: {msg}",
                "progress": int((self.session["frames"]/20)*100)
            })
