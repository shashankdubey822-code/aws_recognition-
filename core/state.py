import sqlite3
import os

DB_PATH = "faces_db/system.db"

def init_db():
    os.makedirs("faces_db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Table for persistent attendance logs
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (name TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # Table for registered faces (local metadata)
    cursor.execute('''CREATE TABLE IF NOT EXISTS registered_faces
                     (name TEXT UNIQUE, date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Global Runtime State (RESTORED FOR COMPATIBILITY)
attendance_memory = [] 
PRESENT_IDENTITIES = {} 
last_seen = {} # Restored
temporal_memory = {} # Restored

# New Enterprise State
consensus_votes = {} # { "FaceID": ["Name", "Name", "Name"] }
last_known_positions = {} # { "FaceID": {"x": x, "y": y, "name": name} }

init_db()
