#!/usr/bin/env python3
"""
Nexus.AI — Headless Raspberry Pi Camera Edge Daemon (Multi-Classroom Edition)
=============================================================================
Automated, bandwidth-efficient camera client for Raspberry Pi / Edge hardware.
Connects via WebSocket to the central attendance server.
- Stands by in low-power mode with camera OFF.
- Automatically wakes up camera when Teacher clicks 'Start Monitoring'.
- Captures and transmits full raw uncropped frames every N seconds.
- Reports device name, classroom ID, and local IP metadata.
- Releases camera when monitoring concludes or teacher stops.
"""

import sys
import os
import time
import json
import base64
import asyncio
import argparse
import socket
import websockets
import cv2

DEFAULT_SERVER_WS = "wss://vrfefavr-hugging-face.hf.space/ws"
DEFAULT_INTERVAL_SEC = 30.0
DEFAULT_CAMERA_INDEX = 0

def get_local_ip():
    """Gets the local network IP address of the device."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class RaspberryPiEdgeClient:
    def __init__(self, server_url: str, device_name: str, device_id: str, hf_token: str = None, interval: float = 30.0, camera_index: int = 0, width: int = 640, height: int = 480):
        self.server_url = server_url
        self.device_name = device_name
        self.device_id = device_id
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.interval = interval
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.local_ip = get_local_ip()
        
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
        """Captures a single raw uncropped frame and encodes it to base64 JPEG string."""
        if not self.cap or not self.cap.isOpened():
            if not self.open_camera():
                return None
        
        # Read frame
        ret, frame = self.cap.read()
        if not ret or frame is None:
            print("⚠️ Failed to grab frame from camera.")
            return None
        
        # Encode to high quality JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        success, buffer = cv2.imencode('.jpg', frame, encode_param)
        if not success:
            return None
            
        b64_str = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"

    async def streaming_loop(self):
        """Streams 1 frame every interval seconds to the server while session is active."""
        print(f"[EDGE STREAM] 🚀 Stream loop started for '{self.device_name}'. Capturing 1 raw frame every {self.interval}s...")
        try:
            while self.session_active and self.is_running:
                start_time = time.time()
                
                # Capture frame in executor thread
                loop = asyncio.get_running_loop()
                frame_data = await loop.run_in_executor(None, self.capture_frame_base64)
                
                if frame_data and self.ws:
                    timestamp = time.strftime("%H:%M:%S")
                    payload = json.dumps({
                        "type": "frame",
                        "device_id": self.device_id,
                        "device_name": self.device_name,
                        "ip": self.local_ip,
                        "image": frame_data
                    })
                    await self.ws.send(payload)
                    print(f"[{timestamp}] 📸 Transmitted RAW uncropped frame ({self.device_name}) -> Server (Next frame in {self.interval}s)")

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
                        print(f"\n[EDGE TRIGGER] ▶️ START MONITORING COMMAND RECEIVED (Duration: {duration} mins)")
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
        print("="*65)
        print("   NEXUS AI — RASPBERRY PI EDGE CAMERA DAEMON")
        print(f"   Device Name : {self.device_name} (ID: {self.device_id})")
        print(f"   Local IP    : {self.local_ip}")
        print(f"   Target Server: {self.server_url}")
        print(f"   Interval    : {self.interval}s (Raw Frame Throttle)")
        print("="*65)

        # Build extra headers if HF token is present
        headers = {}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"

        reconnect_delay = 2
        while self.is_running:
            try:
                print(f"[EDGE] 🔗 Connecting to server at {self.server_url}...")
                
                # Check if websockets library supports additional_headers or extra_headers
                try:
                    ws_ctx = websockets.connect(self.server_url, additional_headers=headers if headers else None, ping_interval=10, ping_timeout=20)
                except TypeError:
                    ws_ctx = websockets.connect(self.server_url, extra_headers=headers if headers else None, ping_interval=10, ping_timeout=20)

                async with ws_ctx as websocket:
                    self.ws = websocket
                    reconnect_delay = 2
                    print("✅ Connected to central server. Registering edge device...")
                    
                    # Register device with custom metadata
                    await websocket.send(json.dumps({
                        "type": "edge_register",
                        "device": self.device_name,
                        "device_id": self.device_id,
                        "ip": self.local_ip
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
    parser.add_argument("--device", default="Raspberry Pi Classroom 01", help="Device name / Classroom Label (default: 'Raspberry Pi Classroom 01')")
    parser.add_argument("--id", default=None, help="Unique Device ID (default: auto-generated from device name)")
    parser.add_argument("--hf-token", default=None, help="Hugging Face User Access Token (if private space)")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC, help=f"Frame interval in seconds (default: {DEFAULT_INTERVAL_SEC}s)")
    parser.add_argument("--camera", type=int, default=DEFAULT_CAMERA_INDEX, help=f"Camera index (default: {DEFAULT_CAMERA_INDEX})")
    parser.add_argument("--width", type=int, default=640, help="Camera width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Camera height (default: 480)")
    
    args = parser.parse_args()
    
    device_id = args.id or f"rpi_{args.device.replace(' ', '_').lower()}"

    client = RaspberryPiEdgeClient(
        server_url=args.url,
        device_name=args.device,
        device_id=device_id,
        hf_token=args.hf_token,
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
