import sqlite3
import os
import time
from datetime import datetime

DB_PATH = "faces_db/system.db"
RAW_FRAMES_DIR = "static/raw_frames"

def init_db():
    os.makedirs("faces_db", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    os.makedirs("static/intruders", exist_ok=True)
    os.makedirs("static/attendees", exist_ok=True)
    os.makedirs(RAW_FRAMES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Table for persistent attendance logs with Roll Number and Session ID
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (roll_number TEXT, name TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, session_id TEXT)''')
    # Table for registered faces (local metadata) with Roll Number
    cursor.execute('''CREATE TABLE IF NOT EXISTS registered_faces
                     (roll_number TEXT, name TEXT, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (roll_number, name))''')
    conn.commit()
    conn.close()

# Global Runtime State
attendance_memory = [] # [{ "roll_number": "...", "name": "...", "time": "..." }]
PRESENT_IDENTITIES = {} 
last_seen = {} # { "identity": timestamp }
temporal_memory = {} 

# Active Monitoring Session State
active_session = {
    "id": None,
    "active": False,
    "duration_minutes": 50,
    "start_time": None,
    "end_time": None,
    "attendees": [] # [{ "roll_number": "...", "name": "...", "time": "...", "photo": "..." }]
}

# Connected & Historical Devices Registry (Supports 30+ Classrooms / Edge Pis)
# device_id -> { "device_id", "device_name", "client_ip", "status", "first_seen", "last_seen", "total_frames", "raw_frames": [...] }
connected_devices = {
    "local_web_browser": {
        "device_id": "local_web_browser",
        "device_name": "Web Browser Host (Local/Remote)",
        "client_ip": "127.0.0.1",
        "status": "standby",
        "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_frames": 0,
        "raw_frames": []
    }
}

# Consensus & Tracking
consensus_votes = {} # { "FaceID": ["Name", "Name", "Name"] }
last_known_positions = {} # { "FaceID": {"x": x, "y": y, "name": name} }

init_db()
