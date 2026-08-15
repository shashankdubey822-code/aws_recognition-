import os
import time
import sqlite3
import threading
from datetime import datetime
from core.config import LOG_FILE, COOL_DOWN_SEC
from core.state import attendance_memory, last_seen, active_session, connected_devices, DB_PATH

# Threading lock to prevent CSV/DB corruption during high-speed recognition
attendance_lock = threading.Lock()

def parse_identity(raw_id: str):
    """
    Parses an AWS external ID or registered string into (name, roll_number).
    Supported formats: 'RollNo__Name', 'Name__RollNo', 'RollNo_Name', 'Name'
    """
    if not raw_id:
        return "Unknown", "N/A"
    
    clean_id = str(raw_id).strip()
    
    if "__" in clean_id:
        parts = clean_id.split("__", 1)
        # Check if first part looks like a roll number (contains digits)
        if any(c.isdigit() for c in parts[0]):
            return parts[1].replace("_", " ").title(), parts[0].strip()
        else:
            return parts[0].replace("_", " ").title(), parts[1].strip()
    elif "_" in clean_id:
        parts = clean_id.split("_")
        # If last part is numeric/roll number
        if parts[-1].isalnum() and any(c.isdigit() for c in parts[-1]) and len(parts) > 1:
            name = " ".join(parts[:-1]).title()
            roll = parts[-1]
            return name, roll
        elif parts[0].isalnum() and any(c.isdigit() for c in parts[0]) and len(parts) > 1:
            roll = parts[0]
            name = " ".join(parts[1:]).title()
            return name, roll
        else:
            return clean_id.replace("_", " ").title(), "N/A"
    else:
        return clean_id.title(), "N/A"

def mark_attendance(raw_identity: str, image_bytes: bytes = None, device_id: str = "edge_device"):
    """Business logic for attendance marking with Roll Number, Device Mapping & active session tracking."""
    now = time.time()
    
    if raw_identity in last_seen and (now - last_seen[raw_identity]) < COOL_DOWN_SEC:
        return "cooldown", None, None, None
        
    last_seen[raw_identity] = now
    
    name, roll_number = parse_identity(raw_identity)
    time_str = datetime.now().strftime("%H:%M:%S")
    date_str = datetime.now().strftime("%Y-%m-%d")
    photo_path = None
    
    with attendance_lock:
        already_present = any(
            (e.get('name') == name and e.get('roll_number') == roll_number) or e.get('name') == name
            for e in attendance_memory
        )
        
        # Save snapshot if image_bytes provided
        if image_bytes and not already_present:
            try:
                os.makedirs("static/attendees", exist_ok=True)
                timestamp_int = int(now)
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_')).replace(" ", "_")
                filename = f"static/attendees/{roll_number}_{safe_name}_{timestamp_int}.jpg"
                with open(filename, "wb") as f:
                    f.write(image_bytes)
                photo_path = f"/{filename}"
            except Exception as e:
                print(f"⚠️ Failed to save attendee photo: {e}")
        
        if not already_present:
            try:
                # 1. Update CSV Log
                if not os.path.exists(LOG_FILE):
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.write("Roll Number,Name,Time,Date,Status,Device\n")
                
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f'"{roll_number}","{name}","{time_str}","{date_str}","CLEARANCE GRANTED","{device_id}"\n')
                
                # 2. Update SQLite Database
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    session_id = active_session["id"] if active_session.get("active") else "GENERAL"
                    cursor.execute("INSERT INTO attendance (roll_number, name, session_id, device_id) VALUES (?, ?, ?, ?)",
                                   (roll_number, name, session_id, device_id))
                    conn.commit()
                    conn.close()
                except Exception as db_err:
                    print(f"⚠️ DB Error: {db_err}")
                
                # 3. Update In-Memory Cache
                entry = {
                    "roll_number": roll_number,
                    "name": name,
                    "time": time_str,
                    "date": date_str,
                    "photo": photo_path,
                    "device_id": device_id
                }
                attendance_memory.insert(0, entry)
                
                # 4. Add to current active monitoring session if running
                if active_session.get("active"):
                    active_session["attendees"].append(entry)

                # 5. Add to Device-Specific Verified Students list
                if device_id in connected_devices:
                    if "verified_students" not in connected_devices[device_id]:
                        connected_devices[device_id]["verified_students"] = []
                    connected_devices[device_id]["verified_students"].insert(0, entry)
                    
                return "success", name, roll_number, time_str
            except Exception as e:
                print(f"🔴 Disk I/O Error: {e}")
                return "error", name, roll_number, None
    
    return "already_marked", name, roll_number, time_str
