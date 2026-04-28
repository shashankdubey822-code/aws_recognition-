import os
import time
import threading
from datetime import datetime
from core.config import LOG_FILE, COOL_DOWN_SEC
from core.state import attendance_memory, last_seen

# Threading lock to prevent CSV corruption during high-speed recognition
attendance_lock = threading.Lock()

def mark_attendance(name: str):
    """Business logic for attendance checking. O(1) complexity via dicts."""
    now = time.time()
    
    if name in last_seen and (now - last_seen[name]) < COOL_DOWN_SEC:
        return "cooldown", None
        
    last_seen[name] = now
    
    with attendance_lock:
        already_present = any(e['name'] == name for e in attendance_memory)
        time_str = datetime.now().strftime("%H:%M:%S")
        
        if not already_present:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{name},{time_str}\n")
                
                entry = {"name": name, "time": time_str}
                attendance_memory.insert(0, entry)
                return "success", time_str
            except Exception as e:
                print(f"🔴 Disk I/O Error: {e}")
                return "error", None
    
    return "already_marked", time_str
