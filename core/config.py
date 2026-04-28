import os
from dotenv import load_dotenv

load_dotenv()

# --- AWS Config ---
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COLLECTION_ID = os.getenv("AWS_COLLECTION_ID", "hackathon_attendance")

# --- Thresholds ---
MATCH_THRESHOLD = 90.0 # AWS confidence threshold out of 100

# --- App Config ---
LOG_FILE = "attendance_log.csv"
LIVE_PRESENCE_TIMEOUT = 5 # Seconds
COOL_DOWN_SEC = 300 # 5 minutes cooldown