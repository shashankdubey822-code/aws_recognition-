import os
from datetime import datetime, timezone, timedelta

# Configurable Timezone - Default: Indian Standard Time (Asia/Kolkata, UTC+5:30)
TIMEZONE_NAME = os.getenv("TIMEZONE", "Asia/Kolkata")

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    # Reliable Fallback for UTC+5:30 (IST)
    LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))

def get_now() -> datetime:
    """Returns the current timezone-aware datetime object in 24-hour local time."""
    return datetime.now(LOCAL_TZ)

def get_time_str() -> str:
    """Returns 24-hour formatted time string e.g. '09:51:24' or '14:30:00'."""
    return get_now().strftime("%H:%M:%S")

def get_date_str() -> str:
    """Returns ISO date string e.g. '2026-08-16'."""
    return get_now().strftime("%Y-%m-%d")

def get_timestamp_full_str() -> str:
    """Returns full timestamp string e.g. '2026-08-16 09:51:24'."""
    return get_now().strftime("%Y-%m-%d %H:%M:%S")

def get_compact_timestamp_str() -> str:
    """Returns compact timestamp for session IDs e.g. '20260816_095124'."""
    return get_now().strftime("%Y%m%d_%H%M%S")
