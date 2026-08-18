"""
Enterprise Email Dispatch & Report Export Service
Supports:
1. Resend HTTPS REST API (Port 443)
2. Standard SMTP Fallback (smtplib + email.mime) with STARTTLS/SSL
3. Multi-Format Report Generation (.xlsx, .csv, .pdf)
4. Comprehensive Error Diagnostics
"""

import os
import json
import base64
import smtplib
import mimetypes
import urllib.request
import urllib.error
import traceback
import pandas as pd
from typing import Union, List, Dict, Tuple, Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders

from core.config import (
    RESEND_API_KEY, TEACHER_REPORT_EMAIL, REPORTS_DIR,
    SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
)
from core.timezone_utils import (
    get_time_str, get_date_str, get_timestamp_full_str, get_compact_timestamp_str
)
from services.pdf_service import generate_session_pdf

# Configurable aliases
SMTP_HOST = os.getenv("SMTP_HOST", os.getenv("SMTP_SERVER", SMTP_SERVER or "smtp.gmail.com"))
SMTP_USER = os.getenv("SMTP_USER", os.getenv("SMTP_EMAIL", SMTP_EMAIL or ""))
SMTP_PASS = os.getenv("SMTP_PASS", os.getenv("SMTP_PASSWORD", SMTP_PASSWORD or ""))
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
SMTP_SENDER_NAME = os.getenv("SMTP_SENDER_NAME", "Anyiiiiie.AI Security & Attendance")

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
                return "".join(lines[-50:])
        except Exception as e:
            return f"Error reading log: {e}"
    return "No email dispatch operations recorded yet."


def generate_session_csv(session_data: Union[dict, str], output_dir: str = REPORTS_DIR) -> str:
    """Generates a standard CSV attendance report for a concluded session in 24-hour IST."""
    os.makedirs(output_dir, exist_ok=True)
    session_id = session_data.get("id", "SESSION") if isinstance(session_data, dict) else str(session_data)
    timestamp = get_compact_timestamp_str()
    filename = f"Attendance_Report_{session_id}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)
    
    attendees = session_data.get("attendees", []) if isinstance(session_data, dict) else []
    rows = []
    for idx, att in enumerate(attendees, 1):
        rows.append({
            "S.No": idx,
            "Roll Number": att.get("roll_number", "N/A"),
            "Student Name": att.get("name", "Unknown"),
            "Time Marked (24h IST)": att.get("time", get_time_str()),
            "Date": att.get("date", get_date_str()),
            "Classroom Node": att.get("device_id", "Classroom 101"),
            "Status": "PRESENT / VERIFIED"
        })
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["S.No", "Roll Number", "Student Name", "Time Marked (24h IST)", "Date", "Classroom Node", "Status"])
    df.to_csv(filepath, index=False, encoding="utf-8")
    return filepath


def generate_session_excel(session_data: Union[dict, str], output_dir: str = REPORTS_DIR) -> str:
    """Generates a styled Excel attendance report for a concluded session in 24-hour IST."""
    os.makedirs(output_dir, exist_ok=True)
    session_id = session_data.get("id", "SESSION") if isinstance(session_data, dict) else str(session_data)
    timestamp = get_compact_timestamp_str()
    filename = f"Attendance_Report_{session_id}_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)
    
    attendees = session_data.get("attendees", []) if isinstance(session_data, dict) else []
    
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
        filepath = os.path.join(output_dir, csv_filename)
        df.to_csv(filepath, index=False)
        
    return filepath


def _build_html_email_body(session_data: dict) -> str:
    """Constructs a responsive HTML email summary template."""
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    duration = session_data.get("duration_minutes", 50)
    current_time_str = get_time_str()
    current_date_str = get_date_str()

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
                <h2 style="margin: 0; font-size: 22px; letter-spacing: 0.5px;">🎓 Anyiiiiie.AI Security & Attendance Report</h2>
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
                    📎 Multi-format audit files (PDF, Excel .xlsx, and CSV) are attached to this email along with surveillance snapshots.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content


def _collect_email_attachments(session_data: dict, extra_paths: Union[str, List[str]] = None) -> List[Dict[str, str]]:
    """Gathers and base64-encodes all report attachments and surveillance frames."""
    attachments = []
    seen_paths = set()

    def add_file(p: str):
        if not p:
            return
        local_p = p[1:] if p.startswith("/") else p
        if local_p in seen_paths or not os.path.exists(local_p):
            return
        seen_paths.add(local_p)
        try:
            with open(local_p, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("utf-8")
                attachments.append({
                    "filename": os.path.basename(local_p),
                    "content": content_b64,
                    "filepath": local_p
                })
        except Exception as e:
            print(f"⚠️ Could not encode attachment {local_p}: {e}")

    # Process extra paths passed explicitly
    if extra_paths:
        if isinstance(extra_paths, str):
            add_file(extra_paths)
        elif isinstance(extra_paths, list):
            for p in extra_paths:
                add_file(p)

    # Process raw surveillance frames from session
    raw_frames = session_data.get("raw_frames", [])
    for frm in raw_frames:
        add_file(frm)

    # Fallback to attendee snapshots if no raw frames
    if not raw_frames:
        for att in session_data.get("attendees", []):
            photo = att.get("photo")
            if photo:
                add_file(photo)

    return attachments


def send_via_resend_api(session_data: dict, target_email: str, attachment_paths: Union[str, List[str]] = None) -> Tuple[bool, str]:
    """Sends email via standard HTTPS REST API (Port 443) using Resend."""
    api_key = (RESEND_API_KEY or "").strip()
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    current_time_str = get_time_str()

    log_email_diagnostic("HTTPS_API", "START", f"Dispatching via Resend HTTPS REST API (Port 443) to {target_email}...")

    if not api_key:
        err_msg = "RESEND_API_KEY is empty. Skipping Resend."
        log_email_diagnostic("HTTPS_API", "CONFIG_ERROR", err_msg)
        return False, err_msg

    html_content = _build_html_email_body(session_data)
    encoded_attachments = _collect_email_attachments(session_data, attachment_paths)

    resend_attachments = [{"filename": a["filename"], "content": a["content"]} for a in encoded_attachments]

    payload_data = {
        "from": "Anyiiiiie.AI Attendance <onboarding@resend.dev>",
        "to": [target_email],
        "subject": f"📊 Attendance Session Report [{session_id}] - {len(attendees)} Present ({current_time_str} IST)",
        "html": html_content,
        "attachments": resend_attachments
    }

    req_url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "AnyiiiiieAI-Attendance/1.0"
    }

    try:
        json_bytes = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(req_url, data=json_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            email_id = res_json.get("id", "OK")
            success_msg = f"✅ EMAIL DELIVERED via Resend HTTPS API (Email ID: {email_id}) to {target_email} with {len(resend_attachments)} attachments"
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


def send_via_smtp(session_data: dict, target_email: str, attachment_paths: Union[str, List[str]] = None) -> Tuple[bool, str]:
    """Sends email via standard RFC SMTP with STARTTLS or SSL using configured credentials."""
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    current_time_str = get_time_str()

    host = (SMTP_HOST or "").strip()
    port = int(SMTP_PORT or 587)
    user = (SMTP_USER or "").strip()
    password = (SMTP_PASS or "").strip()
    use_tls = SMTP_USE_TLS
    use_ssl = SMTP_USE_SSL or (port == 465)

    log_email_diagnostic("SMTP_FALLBACK", "START", f"Dispatching via SMTP ({host}:{port}) to {target_email}...")

    if not host:
        err_msg = "SMTP_HOST / SMTP_SERVER is not configured."
        log_email_diagnostic("SMTP_FALLBACK", "CONFIG_ERROR", err_msg)
        return False, err_msg

    # Build MIME message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"📊 Attendance Session Report [{session_id}] - {len(attendees)} Present ({current_time_str} IST)"
    sender_name = SMTP_SENDER_NAME or "Anyiiiiie.AI Attendance"
    sender_addr = user or f"noreply@{host}"
    msg["From"] = f"{sender_name} <{sender_addr}>"
    msg["To"] = target_email

    # HTML Body
    html_content = _build_html_email_body(session_data)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # Process and attach files
    encoded_attachments = _collect_email_attachments(session_data, attachment_paths)
    for att in encoded_attachments:
        filename = att["filename"]
        local_path = att["filepath"]
        
        content_type, _ = mimetypes.guess_type(local_path)
        if content_type is None:
            content_type = "application/octet-stream"
        main_type, sub_type = content_type.split("/", 1)
        
        try:
            with open(local_path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)
        except Exception as e:
            print(f"⚠️ Could not attach {local_path} to SMTP message: {e}")

    # Transmit via SMTP
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=25)
        else:
            server = smtplib.SMTP(host, port, timeout=25)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()

        if user and password:
            server.login(user, password)

        server.send_message(msg)
        server.quit()

        success_msg = f"✅ EMAIL DELIVERED via Standard SMTP ({host}:{port}) to {target_email} with {len(encoded_attachments)} attachments"
        log_email_diagnostic("SMTP_FALLBACK", "SUCCESS", success_msg)
        return True, success_msg

    except Exception as e:
        err_msg = f"SMTP Transmission Exception ({host}:{port}): {e}"
        log_email_diagnostic("SMTP_FALLBACK", "FAILED", err_msg)
        return False, err_msg


def send_session_email_report(
    session_data: Union[dict, None] = None, 
    recipient: str = None, 
    attachment_paths: Union[str, List[str]] = None,
    **kwargs
) -> Tuple[bool, str]:
    """
    Primary universal router for sending session reports.
    Automatically generates Excel, CSV, and PDF reports, then dispatches via Resend HTTPS API
    with seamless automatic fallback to standard SMTP.
    """
    if session_data is None:
        session_data = {
            "id": kwargs.get("session_id", "LIVE_SESSION"),
            "attendees": kwargs.get("attendees", []),
            "duration_minutes": kwargs.get("duration_minutes", 50),
            "raw_frames": kwargs.get("raw_frames", [])
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
    
    log_email_diagnostic("DISPATCH_TRIGGER", "START", f"Initiating multi-format report dispatch for session '{session_id}' (Attendees: {len(attendees)}, Recipient: {target_email})")

    # 1. Generate All Three Standard Report Formats
    generated_reports = []
    try:
        excel_path = generate_session_excel(session_data)
        if os.path.exists(excel_path):
            generated_reports.append(excel_path)
    except Exception as e:
        print(f"⚠️ Excel generation warning: {e}")

    try:
        csv_path = generate_session_csv(session_data)
        if os.path.exists(csv_path):
            generated_reports.append(csv_path)
    except Exception as e:
        print(f"⚠️ CSV generation warning: {e}")

    try:
        pdf_path = generate_session_pdf(session_data)
        if os.path.exists(pdf_path):
            generated_reports.append(pdf_path)
    except Exception as e:
        print(f"⚠️ PDF generation warning: {e}")

    # Combine with any user-passed attachment paths
    all_attachments = list(generated_reports)
    if attachment_paths:
        if isinstance(attachment_paths, str) and attachment_paths not in all_attachments:
            all_attachments.append(attachment_paths)
        elif isinstance(attachment_paths, list):
            for p in attachment_paths:
                if p not in all_attachments:
                    all_attachments.append(p)

    # 2. Strategy Step 1: Attempt Resend HTTPS REST API
    if RESEND_API_KEY and RESEND_API_KEY.strip():
        log_email_diagnostic("AUTH_ROUTE", "SELECTED", "Attempting primary route via Resend HTTPS API (Port 443)...")
        resend_ok, resend_msg = send_via_resend_api(session_data, target_email, all_attachments)
        if resend_ok:
            return True, resend_msg
        log_email_diagnostic("AUTH_ROUTE", "RESEND_FAILED", f"Resend delivery failed ({resend_msg}). Falling back to SMTP...")

    # 3. Strategy Step 2: Fallback to Standard SMTP
    if SMTP_HOST and SMTP_HOST.strip():
        log_email_diagnostic("AUTH_ROUTE", "SELECTED", "Attempting fallback route via Standard SMTP...")
        smtp_ok, smtp_msg = send_via_smtp(session_data, target_email, all_attachments)
        if smtp_ok:
            return True, smtp_msg
        log_email_diagnostic("AUTH_ROUTE", "SMTP_FAILED", f"SMTP fallback failed: {smtp_msg}")
        return False, f"Email delivery failed across both Resend and SMTP routes. (SMTP error: {smtp_msg})"

    # Neither service was usable
    err_msg = "🚨 No valid email credentials configured (neither RESEND_API_KEY nor SMTP_HOST/SMTP_USER is set)."
    log_email_diagnostic("AUTH_ROUTE", "NO_CREDENTIALS", err_msg)
    return False, err_msg


# Backward-compatibility alias
send_attendance_email = send_session_email_report
