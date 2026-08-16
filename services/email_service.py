import os
import json
import base64
import urllib.request
import urllib.error
import traceback
import pandas as pd
from datetime import datetime

from core.config import RESEND_API_KEY, TEACHER_REPORT_EMAIL, REPORTS_DIR
from core.timezone_utils import get_time_str, get_date_str, get_timestamp_full_str, get_compact_timestamp_str

DIAGNOSTICS_FILE = os.path.join(REPORTS_DIR, "email_error_diagnostics.txt")

def log_email_diagnostic(stage: str, status: str, details: str):
    """Writes detailed step-by-step diagnostic trace to dedicated error file."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = get_timestamp_full_str()
    log_line = f"[{timestamp}] [{stage}] [{status}] {details}\n"
    print(log_line.strip())
    try:
        with open(DIAGNOSTICS_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"Failed writing to email log file: {e}")

def get_latest_email_diagnostics() -> str:
    """Reads the dedicated email diagnostic log."""
    if os.path.exists(DIAGNOSTICS_FILE):
        try:
            with open(DIAGNOSTICS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return "".join(lines[-40:])
        except Exception as e:
            return f"Error reading log: {e}"
    return "No email dispatch operations recorded yet."

def generate_session_excel(session_data: dict) -> str:
    """Generates a styled Excel attendance report for a concluded session in 24-hour IST."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    session_id = session_data.get("id", "SESSION")
    timestamp = get_compact_timestamp_str()
    filename = f"Attendance_Report_{session_id}_{timestamp}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)
    
    attendees = session_data.get("attendees", [])
    
    rows = []
    for idx, att in enumerate(attendees, 1):
        rows.append({
            "S.No": idx,
            "Roll Number": att.get("roll_number", "N/A"),
            "Student Name": att.get("name", "Unknown"),
            "Time Marked (24h IST)": att.get("time", get_time_str()),
            "Date": att.get("date", get_date_str()),
            "Classroom Node": att.get("device_id", "Classroom 101"),
            "Status": "PRESENT / VERIFIED ✓"
        })
    
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["S.No", "Roll Number", "Student Name", "Time Marked (24h IST)", "Date", "Classroom Node", "Status"])
        
    try:
        df.to_excel(filepath, index=False, sheet_name="Attendance_Session")
    except Exception as e:
        csv_filename = f"Attendance_Report_{session_id}_{timestamp}.csv"
        filepath = os.path.join(REPORTS_DIR, csv_filename)
        df.to_csv(filepath, index=False)
        
    return filepath

def send_via_resend_api(session_data: dict, target_email: str, report_path: str) -> tuple[bool, str]:
    """Sends email via standard HTTPS REST API (Port 443) using Resend with 24h IST formatting."""
    api_key = (RESEND_API_KEY or "").strip()
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    duration = session_data.get("duration_minutes", 50)
    current_time_str = get_time_str()
    current_date_str = get_date_str()
    
    log_email_diagnostic("HTTPS_API", "START", f"Dispatching via Resend HTTPS REST API (Port 443) to {target_email}...")
    
    if not api_key:
        err_msg = "🚨 RESEND_API_KEY is empty. Please set 'RESEND_API_KEY' in Hugging Face Space Settings -> Variables and secrets."
        log_email_diagnostic("HTTPS_API", "CONFIG_ERROR", err_msg)
        return False, err_msg

    # 1. Build HTML Body
    table_rows = ""
    for idx, att in enumerate(attendees, 1):
        table_rows += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 10px; text-align: center; color: #64748b;">{idx}</td>
            <td style="padding: 10px; font-weight: bold; color: #0284c7;">{att.get('roll_number', 'N/A')}</td>
            <td style="padding: 10px; font-weight: 600; color: #1e293b;">{att.get('name', 'Unknown')}</td>
            <td style="padding: 10px; text-align: center; color: #475569; font-weight: bold;">{att.get('time', current_time_str)}</td>
            <td style="padding: 10px; text-align: center; color: #16a34a; font-weight: bold;">VERIFIED ✓</td>
        </tr>
        """
        
    if not attendees:
        table_rows = '<tr><td colspan="5" style="padding: 20px; text-align: center; color: #94a3b8;">No students recorded during this session.</td></tr>'

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b;">
        <div style="max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #0284c7, #0f172a); padding: 24px; color: white;">
                <h2 style="margin: 0; font-size: 22px; letter-spacing: 0.5px;">🎓 Nexus AI Security & Attendance Report</h2>
                <p style="margin: 6px 0 0 0; opacity: 0.85; font-size: 13px;">Classroom Monitoring Session Summary (24-Hour IST)</p>
            </div>
            
            <div style="padding: 24px;">
                <div style="display: flex; gap: 15px; margin-bottom: 20px; background: #f1f5f9; padding: 15px; border-radius: 8px;">
                    <div style="flex: 1;">
                        <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Session ID</span>
                        <div style="font-weight: bold; font-size: 14px;">{session_id}</div>
                    </div>
                    <div style="flex: 1;">
                        <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Duration</span>
                        <div style="font-weight: bold; font-size: 14px;">{duration} Minutes</div>
                    </div>
                    <div style="flex: 1;">
                        <span style="font-size: 11px; color: #64748b; text-transform: uppercase;">Total Present</span>
                        <div style="font-weight: bold; font-size: 14px; color: #16a34a;">{len(attendees)} Students</div>
                    </div>
                </div>

                <div style="font-size: 12px; color: #64748b; margin-bottom: 15px;">
                    📅 <strong>Report Generated:</strong> {current_date_str} at <strong>{current_time_str} (IST)</strong>
                </div>
                
                <h3 style="font-size: 15px; margin-bottom: 12px; color: #334155;">Verified Attendance Ledger</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; color: #475569; text-transform: uppercase; font-size: 11px;">
                            <th style="padding: 10px; text-align: center;">S.No</th>
                            <th style="padding: 10px; text-align: left;">Roll No</th>
                            <th style="padding: 10px; text-align: left;">Student Name</th>
                            <th style="padding: 10px; text-align: center;">Time (24h IST)</th>
                            <th style="padding: 10px; text-align: center;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
                
                <p style="margin-top: 25px; font-size: 12px; color: #64748b; line-height: 1.5;">
                    📎 The full Excel report file is attached to this email along with biometric verification snapshots.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # 2. Encode Attachments
    attachments = []
    
    # Attach Excel Workbook
    if os.path.exists(report_path):
        with open(report_path, "rb") as f:
            b64_content = base64.b64encode(f.read()).decode("utf-8")
            attachments.append({
                "filename": os.path.basename(report_path),
                "content": b64_content
            })

    # Attach ALL Uncropped Raw Surveillance Frames from Raspberry Pi
    raw_frames = session_data.get("raw_frames", [])
    attached_raw_count = 0
    for frame_path in raw_frames:
        f_local = frame_path[1:] if frame_path.startswith("/") else frame_path
        if os.path.exists(f_local):
            try:
                with open(f_local, "rb") as img_file:
                    b64_img = base64.b64encode(img_file.read()).decode("utf-8")
                    attachments.append({
                        "filename": os.path.basename(f_local),
                        "content": b64_img
                    })
                    attached_raw_count += 1
            except Exception as e:
                print(f"Could not attach uncropped frame {f_local}: {e}")

    # Fallback to attendee snapshots if no raw frames list was passed
    if attached_raw_count == 0:
        for att in attendees:
            photo_rel = att.get("photo")
            if photo_rel:
                photo_local = photo_rel[1:] if photo_rel.startswith("/") else photo_rel
                if os.path.exists(photo_local):
                    try:
                        with open(photo_local, "rb") as img_file:
                            b64_img = base64.b64encode(img_file.read()).decode("utf-8")
                            attachments.append({
                                "filename": os.path.basename(photo_local),
                                "content": b64_img
                            })
                    except Exception as e:
                        print(f"Could not attach snapshot {photo_local}: {e}")

    # 3. Payload for Resend HTTPS API
    payload_data = {
        "from": "Nexus AI Attendance <onboarding@resend.dev>",
        "to": [target_email],
        "subject": f"📊 Attendance Session Report [{session_id}] - {len(attendees)} Present ({current_time_str} IST)",
        "html": html_content,
        "attachments": attachments
    }

    req_url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "NexusAI-Attendance/1.0"
    }

    try:
        json_bytes = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(req_url, data=json_bytes, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=20) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            email_id = res_json.get("id", "OK")
            
            success_msg = f"✅ EMAIL DELIVERED via Resend HTTPS API (Email ID: {email_id}) to {target_email} with {len(attachments)} attachments"
            log_email_diagnostic("HTTPS_API", "SUCCESS", success_msg)
            return True, success_msg

    except urllib.error.HTTPError as he:
        err_response = he.read().decode("utf-8") if he.fp else str(he)
        err_msg = f"Resend API Error (HTTP {he.code}): {err_response}"
        log_email_diagnostic("HTTPS_API", "FAILED", err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Resend API Request Exception: {e}"
        log_email_diagnostic("HTTPS_API", "FAILED", err_msg)
        return False, err_msg

def send_session_email_report(session_data: dict = None, recipient: str = None, **kwargs) -> tuple[bool, str]:
    """
    Primary universal router for sending session reports.
    Accepts either a dict `session_data` or individual kwargs (`session_id`, `attendees`, `duration_minutes`).
    """
    if session_data is None:
        session_data = {
            "id": kwargs.get("session_id", "LIVE_SESSION"),
            "attendees": kwargs.get("attendees", []),
            "duration_minutes": kwargs.get("duration_minutes", 50)
        }
    elif isinstance(session_data, dict):
        if "id" not in session_data and "session_id" in kwargs:
            session_data["id"] = kwargs["session_id"]
        if "attendees" not in session_data and "attendees" in kwargs:
            session_data["attendees"] = kwargs["attendees"]
        if "duration_minutes" not in session_data and "duration_minutes" in kwargs:
            session_data["duration_minutes"] = kwargs["duration_minutes"]

    target_email = recipient or TEACHER_REPORT_EMAIL
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    
    log_email_diagnostic("DISPATCH_TRIGGER", "START", f"Initiating report dispatch for session '{session_id}' (Total Attendees: {len(attendees)}, Recipient: {target_email})")
    
    report_path = generate_session_excel(session_data)
    log_email_diagnostic("REPORT_GENERATION", "SUCCESS", f"Generated workbook at '{report_path}'")

    # 1. Primary: Direct HTTPS REST API (Port 443) via Resend
    if RESEND_API_KEY and RESEND_API_KEY.strip():
        log_email_diagnostic("AUTH_ROUTE", "SELECTED", "Using RESEND_API_KEY over standard HTTPS (Port 443).")
        return send_via_resend_api(session_data, target_email, report_path)
    else:
        err_msg = "🚨 RESEND_API_KEY is not configured! Please add 'RESEND_API_KEY' in Hugging Face Settings -> Variables and secrets."
        log_email_diagnostic("AUTH_ROUTE", "MISSING_KEY", err_msg)
        return False, err_msg
