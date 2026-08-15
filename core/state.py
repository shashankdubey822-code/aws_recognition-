import sqlite3
import os
import time

DB_PATH = "faces_db/system.db"

def init_db():
    os.makedirs("faces_db", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    os.makedirs("static/intruders", exist_ok=True)
    os.makedirs("static/attendees", exist_ok=True)
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

# Connected Edge Devices (e.g. Raspberry Pi)
connected_edge_clients = set()

# Consensus & Tracking
consensus_votes = {} # { "FaceID": ["Name", "Name", "Name"] }
last_known_positions = {} # { "FaceID": {"x": x, "y": y, "name": name} }

init_db()
