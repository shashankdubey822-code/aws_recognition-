#!/usr/bin/env python3
"""
Nexus.AI — Headless Raspberry Pi Camera Edge Daemon
=====================================================
Automated, bandwidth-efficient camera client for Raspberry Pi / Edge hardware.
Connects via WebSocket to the central attendance server.
- Stands by in low-power mode with camera OFF.
- Automatically wakes up camera when Teacher clicks 'Start Monitoring'.
- Captures and transmits 1 frame every 30 seconds (configurable rate-limiting).
- Releases camera when monitoring concludes or teacher stops.
"""

import sys
import time
import json
import base64
import asyncio
import argparse
import websockets
import cv2

DEFAULT_SERVER_WS = "ws://localhost:7860/ws"
DEFAULT_INTERVAL_SEC = 30.0
DEFAULT_CAMERA_INDEX = 0

class RaspberryPiEdgeClient:
    def __init__(self, server_url: str, interval: float = 30.0, camera_index: int = 0, width: int = 640, height: int = 480):
        self.server_url = server_url
        self.interval = interval
        self.camera_index = camera_index
        self.width = width
        self.height = height
        
        self.is_running = True
        self.session_active = False
        self.cap = None
        self.ws = None
        self.capture_task = None

    def open_camera(self):
        """Initializes and opens local camera hardware."""
        if self.cap is not None and self.cap.isOpened():
            return True
        print(f"[EDGE CAMERA] 📷 Initializing camera index {self.camera_index} ({self.width}x{self.height})...")
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if self.cap.isOpened():
                print("✅ Camera hardware initialized and active.")
                return True
            else:
                print(f"❌ Could not open camera on index {self.camera_index}.")
                return False
        except Exception as e:
            print(f"❌ Camera init error: {e}")
            return False

    def release_camera(self):
        """Releases camera hardware to save CPU and power."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            print("🛑 Camera released. Device in low-power STANDBY mode.")

    def capture_frame_base64(self) -> str | None:
        """Captures a single frame and encodes it to base64 JPEG string."""
        if not self.cap or not self.cap.isOpened():
            if not self.open_camera():
                return None
        
        # Read frame
        ret, frame = self.cap.read()
        if not ret or frame is None:
            print("⚠️ Failed to grab frame from camera.")
            return None
        
        # Encode to JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        success, buffer = cv2.imencode('.jpg', frame, encode_param)
        if not success:
            return None
            
        b64_str = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"

    async def streaming_loop(self):
        """Streams 1 frame every interval seconds to the server while session is active."""
        print(f"[EDGE STREAM] 🚀 Stream loop started. Capturing 1 frame every {self.interval}s...")
        try:
            while self.session_active and self.is_running:
                start_time = time.time()
                
                # Capture frame in executor thread to prevent blocking asyncio loop
                loop = asyncio.get_running_loop()
                frame_data = await loop.run_in_executor(None, self.capture_frame_base64)
                
                if frame_data and self.ws:
                    timestamp = time.strftime("%H:%M:%S")
                    payload = json.dumps({"type": "frame", "image": frame_data})
                    await self.ws.send(payload)
                    print(f"[{timestamp}] 📸 Transmitted frame to AWS AI Subsystem (Next frame in {self.interval}s)")

                # Sleep remaining time
                elapsed = time.time() - start_time
                sleep_time = max(0.5, self.interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            print("[EDGE STREAM] Stream loop halted.")
        except Exception as e:
            print(f"[EDGE STREAM] Streaming error: {e}")

    async def handle_messages(self):
        """Listens for server commands over WebSocket."""
        async for raw_message in self.ws:
            try:
                data = json.loads(raw_message)
                mtype = data.get("type")

                if mtype in ("session_started", "edge_ack"):
                    active = data.get("session_active", True) if mtype == "edge_ack" else True
                    duration = data.get("duration_minutes", 50)
                    
                    if active and not self.session_active:
                        self.session_active = True
                        print(f"\n[EDGE TRIGGER] ▶️ START COMMAND RECEIVED (Duration: {duration} mins)")
                        self.open_camera()
                        if self.capture_task and not self.capture_task.done():
                            self.capture_task.cancel()
                        self.capture_task = asyncio.create_task(self.streaming_loop())

                elif mtype == "session_stopped":
                    print(f"\n[EDGE TRIGGER] 🛑 STOP COMMAND RECEIVED. Reason: {data.get('reason', 'N/A')}")
                    self.session_active = False
                    if self.capture_task and not self.capture_task.done():
                        self.capture_task.cancel()
                    self.release_camera()

                elif mtype == "session_status":
                    if data.get("active") and not self.session_active:
                        self.session_active = True
                        print(f"\n[EDGE TRIGGER] ▶️ Resuming active class session...")
                        self.open_camera()
                        if self.capture_task and not self.capture_task.done():
                            self.capture_task.cancel()
                        self.capture_task = asyncio.create_task(self.streaming_loop())
                    elif not data.get("active") and self.session_active:
                        self.session_active = False
                        if self.capture_task and not self.capture_task.done():
                            self.capture_task.cancel()
                        self.release_camera()

            except Exception as e:
                print(f"Message parsing error: {e}")

    async def run(self):
        """Main lifecycle loop with auto-reconnect."""
        print("="*60)
        print("   NEXUS AI — RASPBERRY PI EDGE CAMERA DAEMON")
        print(f"   Target Server: {self.server_url}")
        print(f"   Frame Interval: {self.interval}s (AWS Rate Limiting Bucket)")
        print("="*60)

        reconnect_delay = 2
        while self.is_running:
            try:
                print(f"[EDGE] 🔗 Connecting to server at {self.server_url}...")
                async with websockets.connect(self.server_url, ping_interval=10, ping_timeout=20) as websocket:
                    self.ws = websocket
                    reconnect_delay = 2
                    print("✅ Connected to central server. Registering edge device...")
                    
                    # Register device
                    await websocket.send(json.dumps({
                        "type": "edge_register",
                        "device": "RaspberryPi_Classroom_Camera"
                    }))

                    # Request session status
                    await websocket.send(json.dumps({"type": "get_session_status"}))

                    print("📡 Standing by in Low-Power Mode for Teacher Start Trigger...")
                    await self.handle_messages()

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                print(f"⚠️ Connection dropped ({e}). Reconnecting in {reconnect_delay}s...")
                self.session_active = False
                if self.capture_task and not self.capture_task.done():
                    self.capture_task.cancel()
                self.release_camera()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(30, reconnect_delay * 2)

            except Exception as e:
                print(f"🔴 Unexpected error: {e}")
                await asyncio.sleep(3)

def main():
    parser = argparse.ArgumentParser(description="Nexus AI Raspberry Pi Edge Camera Daemon")
    parser.add_argument("--url", default=DEFAULT_SERVER_WS, help=f"WebSocket server URL (default: {DEFAULT_SERVER_WS})")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC, help=f"Frame interval in seconds (default: {DEFAULT_INTERVAL_SEC}s)")
    parser.add_argument("--camera", type=int, default=DEFAULT_CAMERA_INDEX, help=f"Camera index (default: {DEFAULT_CAMERA_INDEX})")
    parser.add_argument("--width", type=int, default=640, help="Camera width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Camera height (default: 480)")
    
    args = parser.parse_args()

    client = RaspberryPiEdgeClient(
        server_url=args.url,
        interval=args.interval,
        camera_index=args.camera,
        width=args.width,
        height=args.height
    )

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n🛑 Exiting edge client. Goodbye!")
        client.release_camera()
        sys.exit(0)

if __name__ == "__main__":
    main()
