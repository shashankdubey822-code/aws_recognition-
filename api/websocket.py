import json
import os
from fastapi import WebSocket, WebSocketDisconnect

os.makedirs("static/intruders", exist_ok=True)
from services.liveness_engine import warmup
from api.controllers.registration_controller import RegistrationController
from api.controllers.tracking_controller import TrackingController

# Pre-warm MiniFASNet model into RAM on startup
try:
    warmup()
except Exception as e:
    print(f"[LIVENESS] Warmup skipped: {e}")

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    registration_controller = RegistrationController(websocket)
    tracking_controller = TrackingController(websocket)
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                payload = json.loads(data)

                if payload.get("type") == "start_registration":
                    registration_controller.start_registration(payload)
                    continue

                if payload.get("type") == "register_frame":
                    await registration_controller.process_frame(payload)
                    continue

                if payload.get("type") == "frame":
                    await tracking_controller.process_frame(payload)

            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "close" in str(e).lower():
                    break
                print(f"Frame Error: {e}")
                try: await websocket.send_json({"type": "error", "message": f"Frame Error: {str(e)}"})
                except: pass
            except Exception as e:
                print(f"Frame Error: {e}")
                try: await websocket.send_json({"type": "error", "message": f"Frame Processing Error: {str(e)}"})
                except: pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS Fatal Error: {e}")
