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

# --- App & Session Config ---
LOG_FILE = "attendance_log.csv"
REPORTS_DIR = "reports"
LIVE_PRESENCE_TIMEOUT = 5 # Seconds
COOL_DOWN_SEC = 300 # 5 minutes cooldown
DEFAULT_SESSION_DURATION_MIN = 50 # Default monitoring duration: 50 mins
FRAME_RATE_LIMIT_SEC = 30.0 # 30 seconds interval between frame processing/AWS pings

# --- Teacher Authentication ---
TEACHER_EMAIL = os.getenv("TEACHER_EMAIL", "teacher@school.com")
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "nexus_secret_key_attendance_ai_2025")
SESSION_COOKIE_NAME = "nexus_teacher_session"

# --- SMTP Email Configuration ---
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "") # e.g. your_email@gmail.com
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "") # e.g. your_app_password
TEACHER_REPORT_EMAIL = os.getenv("TEACHER_REPORT_EMAIL", "teacher@school.com")