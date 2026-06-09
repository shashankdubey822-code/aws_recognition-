import base64
import asyncio
import sqlite3
import random
from fastapi import WebSocket

from services.aws_client import search_face_on_aws, register_face_to_aws
from services.face_detector import detect_faces_crowd
from core.state import DB_PATH

class RegistrationController:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session = None

    def start_registration(self, payload: dict):
        name = payload.get("name")
        seq = random.sample(["LEFT", "RIGHT", "UP", "DOWN"], 3)
        self.session = {"name": name, "frames": 0, "sequence": seq}

    async def process_frame(self, payload: dict):
        if not self.session:
            return
        if self.session["frames"] >= 20:
            return

        encoded_data = payload["image"].split(',')[1]
        image_bytes = base64.b64decode(encoded_data)
        faces = await asyncio.to_thread(detect_faces_crowd, image_bytes)
        
        if not faces:
            await self.websocket.send_json({"type": "registration_waiting", "message": "🔍 No face detected", "progress": int((self.session["frames"]/20)*100)})
            return

        face = faces[0]
        
        # Environmental Coaching
        brightness = face.get("brightness", 100)
        blur = face.get("blur", 100)
        if brightness < 40:
            await self.websocket.send_json({"type": "registration_waiting", "message": "Lighting too dark. Move to a brighter area.", "progress": int((self.session["frames"]/20)*100)})
            return
        if blur < 50:
            await self.websocket.send_json({"type": "registration_waiting", "message": "Camera out of focus. Please hold still.", "progress": int((self.session["frames"]/20)*100)})
            return

        # Active Liveness
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
                    await self.websocket.send_json({"type": "registration_waiting", "message": "Maintain Center Lock. Look straight ahead.", "progress": int((frames/20)*100)})
                    return
            else:
                step = 0
                if 5 <= frames < 10: step = 0
                elif 10 <= frames < 15: step = 1
                elif 15 <= frames < 20: step = 2
                
                current_challenge = self.session.get("sequence", ["LEFT", "RIGHT", "UP"])[step]
                
                if current_challenge == "LEFT":
                    if nose_rel_x < 0.55: 
                        await self.websocket.send_json({"type": "registration_waiting", "message": "Turn head LEFT to continue.", "progress": int((frames/20)*100)})
                        return
                elif current_challenge == "RIGHT":
                    if nose_rel_x > 0.45:
                        await self.websocket.send_json({"type": "registration_waiting", "message": "Turn head RIGHT to continue.", "progress": int((frames/20)*100)})
                        return
                elif current_challenge == "UP":
                    if nose_rel_y > 0.45:
                        await self.websocket.send_json({"type": "registration_waiting", "message": "Tilt head UP to continue.", "progress": int((frames/20)*100)})
                        return
                elif current_challenge == "DOWN":
                    if nose_rel_y < 0.55:
                        await self.websocket.send_json({"type": "registration_waiting", "message": "Tilt head DOWN to continue.", "progress": int((frames/20)*100)})
                        return

        # Identity Guard
        if self.session["frames"] == 0:
            search_results = await asyncio.to_thread(search_face_on_aws, face["bytes"])
            if search_results and any(res["status"] == "match" for res in search_results):
                match_name = next(res["name"] for res in search_results if res["status"] == "match")
                await self.websocket.send_json({
                    "type": "registration_error", 
                    "message": f"Identity Conflict: This person is already registered as '{match_name.replace('_', ' ')}'."
                })
                self.session = None
                return

        success, msg = await asyncio.to_thread(register_face_to_aws, face["bytes"], self.session["name"])
        if success:
            self.session["frames"] += 1
            progress = int((self.session["frames"]/20)*100)
            await self.websocket.send_json({"type": "registration_status", "message": f"Angle {self.session['frames']}/20 Secured ✓", "progress": progress})
            if self.session["frames"] >= 20:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT OR IGNORE INTO registered_faces (name) VALUES (?)", (self.session["name"],))
                conn.commit(); conn.close()
                await self.websocket.send_json({"type": "registration_success", "message": f"✅ {self.session['name']} profile persistent."})
                self.session = None
