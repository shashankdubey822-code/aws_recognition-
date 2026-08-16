import os
import time
import sqlite3
import threading
from core.config import LOG_FILE, COOL_DOWN_SEC
from core.state import attendance_memory, last_seen, active_session, connected_devices, DB_PATH
from core.timezone_utils import get_time_str, get_date_str, get_now

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
        if any(c.isdigit() for c in parts[0]):
            return parts[1].replace("_", " ").title(), parts[0].strip()
        else:
            return parts[0].replace("_", " ").title(), parts[1].strip()
    elif "_" in clean_id:
        parts = clean_id.split("_")
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
    """
    Marks attendance for a verified student in 24-hour IST local time.
    Tracks attendance per active session and per classroom device node.
    """
    now_epoch = time.time()
    name, roll_number = parse_identity(raw_identity)
    time_str = get_time_str() # 24-hour local time (e.g. 09:51:24)
    date_str = get_date_str() # Local date (e.g. 2026-08-16)
    photo_path = None
    
    with attendance_lock:
        # Check if student is already verified in this active session
        is_already_in_session = False
        if active_session.get("active"):
            is_already_in_session = any(
                (e.get('name') == name and e.get('roll_number') == roll_number) or e.get('name') == name
                for e in active_session.get("attendees", [])
            )
            
        # Check if student is already in this specific classroom's verified list
        is_already_in_device = False
        if device_id in connected_devices:
            is_already_in_device = any(
                (s.get('name') == name and s.get('roll_number') == roll_number) or s.get('name') == name
                for s in connected_devices[device_id].get("verified_students", [])
            )

        # If already marked in current active session, return without duplicating
        if is_already_in_session and is_already_in_device:
            return "already_marked", name, roll_number, time_str

        # 1. Save student snapshot photo safely
        if image_bytes:
            try:
                os.makedirs("static/attendees", exist_ok=True)
                timestamp_int = int(now_epoch)
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_')).replace(" ", "_")
                safe_roll = "".join(c for c in roll_number if c.isalnum() or c in ('_', '-')) or "NA"
                filename = f"static/attendees/{safe_roll}_{safe_name}_{timestamp_int}.jpg"
                with open(filename, "wb") as f:
                    f.write(image_bytes)
                photo_path = f"/{filename}"
            except Exception as e:
                print(f"⚠️ Failed to save attendee photo: {e}")

        # 2. Construct entry with 24-hour IST timestamp
        entry = {
            "roll_number": roll_number,
            "name": name,
            "time": time_str,
            "date": date_str,
            "photo": photo_path,
            "device_id": device_id
        }

        # 3. Add to In-Memory Global List (Top of list)
        attendance_memory.insert(0, entry)
        
        # 4. Add to Active Monitoring Session
        if active_session.get("active"):
            if not is_already_in_session:
                active_session["attendees"].append(entry)

        # 5. Add to Device-Specific Verified Students List
        if device_id in connected_devices:
            if "verified_students" not in connected_devices[device_id]:
                connected_devices[device_id]["verified_students"] = []
            if not is_already_in_device:
                connected_devices[device_id]["verified_students"].insert(0, entry)

        # 6. Write to CSV Log
        try:
            if not os.path.exists(LOG_FILE):
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("Roll Number,Name,Time,Date,Status,Device\n")
            
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f'"{roll_number}","{name}","{time_str}","{date_str}","CLEARANCE GRANTED","{device_id}"\n')
        except Exception as e:
            print(f"⚠️ CSV Write Error: {e}")

        # 7. Write to SQLite Database
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

        print(f"✅ [ATTENDANCE MARKED] {name} (Roll: {roll_number}) via {device_id} at {time_str} IST")
        return "success", name, roll_number, time_str
