import os
from dotenv import load_dotenv

load_dotenv()

# --- AWS Config ---
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COLLECTION_ID = os.getenv("AWS_COLLECTION_ID", "hackathon_attendance")

# --- Thresholds & Security ---
MATCH_THRESHOLD = 98.0  # Increased for Enterprise Security (prevents false positives)
MIN_FACE_AREA = 0.03    # Ignore faces smaller than 3% of the screen (posters, backgrounds)

# --- App Config ---
LOG_FILE = "attendance_log.csv"
LIVE_PRESENCE_TIMEOUT = 5 # Seconds
COOL_DOWN_SEC = 300 # 5 minutes cooldown