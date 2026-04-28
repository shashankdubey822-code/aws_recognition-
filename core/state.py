# Global Application State
attendance_memory = [] # Historical logs (last 50-100)
PRESENT_IDENTITIES = {} # { "Name": last_seen_time }
last_seen = {} # { "Name": last_seen_time } for cooldown logic

# Simple temporal smoothing (Optional with AWS, as it's highly accurate, but good for UI stability)
temporal_memory = {}