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
    os.makedirs("static/crops", exist_ok=True)
    os.makedirs(RAW_FRAMES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Attendance Ledger Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (roll_number TEXT, name TEXT, time TEXT, session_id TEXT, device_id TEXT)''')
    
    # Migration guard: ensure missing columns exist in attendance table
    cursor.execute("PRAGMA table_info(attendance)")
    cols = [col[1] for col in cursor.fetchall()]
    if "device_id" not in cols:
        cursor.execute("ALTER TABLE attendance ADD COLUMN device_id TEXT")
    if "session_id" not in cols:
        cursor.execute("ALTER TABLE attendance ADD COLUMN session_id TEXT")

    # 2. Registered Faces Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS registered_faces
                     (roll_number TEXT, name TEXT, date_added TEXT, PRIMARY KEY (roll_number, name))''')

    # 3. Dedicated Sessions Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (session_id TEXT PRIMARY KEY,
                      start_time TEXT NOT NULL,
                      end_time TEXT,
                      duration_minutes INTEGER NOT NULL,
                      status TEXT NOT NULL,
                      total_attendees INTEGER DEFAULT 0,
                      created_at TEXT NOT NULL)''')

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

# Global In-Flight AWS Tracking Counter
in_flight_aws_tasks = 0

init_db()
