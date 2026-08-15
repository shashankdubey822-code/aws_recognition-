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
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (roll_number TEXT, name TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, session_id TEXT, device_id TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS registered_faces
                     (roll_number TEXT, name TEXT, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (roll_number, name))''')
    conn.commit()
    conn.close()

# Global WebSocket Connections
active_connections = set()

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
    "attendees": []
}

# Connected & Historical Devices Registry (Supports 30+ Classrooms / Edge Pis)
connected_devices = {}

# Consensus & Tracking
consensus_votes = {}
last_known_positions = {}

init_db()
