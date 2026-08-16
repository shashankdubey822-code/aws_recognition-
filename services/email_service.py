import os
import socket
import ssl
import smtplib
import traceback
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders

from core.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD, 
    TEACHER_REPORT_EMAIL, REPORTS_DIR
)

DIAGNOSTICS_FILE = os.path.join(REPORTS_DIR, "email_error_diagnostics.txt")

def log_email_diagnostic(stage: str, status: str, details: str):
    """Writes detailed step-by-step diagnostic trace to dedicated error file."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """Generates a styled Excel / CSV attendance report for a concluded session."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    session_id = session_data.get("id", "SESSION")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Attendance_Report_{session_id}_{timestamp}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)
    
    attendees = session_data.get("attendees", [])
    
    rows = []
    for idx, att in enumerate(attendees, 1):
        rows.append({
            "S.No": idx,
            "Roll Number": att.get("roll_number", "N/A"),
            "Student Name": att.get("name", "Unknown"),
            "Time Marked": att.get("time", ""),
            "Date": att.get("date", datetime.now().strftime("%Y-%m-%d")),
            "Status": "PRESENT / VERIFIED"
        })
    
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["S.No", "Roll Number", "Student Name", "Time Marked", "Date", "Status"])
        
    try:
        df.to_excel(filepath, index=False, sheet_name="Attendance_Session")
    except Exception as e:
        csv_filename = f"Attendance_Report_{session_id}_{timestamp}.csv"
        filepath = os.path.join(REPORTS_DIR, csv_filename)
        df.to_csv(filepath, index=False)
        
    return filepath

def get_smtp_connection():
    """
    Establishes a resilient SMTP connection.
    Enforces IPv4 to resolve Linux Docker 'Network is unreachable' [Errno 101] errors,
    and attempts Port 465 (SSL) first, followed by Port 587 (STARTTLS).
    """
    server_host = SMTP_SERVER or "smtp.gmail.com"
    
    # 1. Resolve host strictly to IPv4 address to prevent IPv6 unreachable routing error
    ipv4_address = server_host
    try:
        addr_info = socket.getaddrinfo(server_host, None, socket.AF_INET, socket.SOCK_STREAM)
        if addr_info:
            ipv4_address = addr_info[0][4][0]
            log_email_diagnostic("DNS_RESOLVE", "SUCCESS", f"Resolved {server_host} -> IPv4 {ipv4_address}")
    except Exception as dns_err:
        log_email_diagnostic("DNS_RESOLVE", "WARNING", f"Could not force IPv4 resolution: {dns_err}")

    # Strategy A: Try Port 465 (SMTPS with direct SSL)
    try:
        log_email_diagnostic("SMTP_CONNECT", "TRY_PORT_465_SSL", f"Attempting direct SSL connection to {server_host} (Port 465)...")
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(server_host, 465, context=context, timeout=15)
        log_email_diagnostic("SMTP_CONNECT", "SUCCESS", "Connected securely via Port 465 (SSL)!")
        return server
    except Exception as e465:
        log_email_diagnostic("SMTP_CONNECT", "FALLBACK", f"Port 465 failed ({e465}). Trying Port 587 STARTTLS...")

    # Strategy B: Try Port 587 (STARTTLS)
    try:
        log_email_diagnostic("SMTP_CONNECT", "TRY_PORT_587_TLS", f"Attempting STARTTLS connection to {server_host} (Port 587)...")
        server = smtplib.SMTP(server_host, 587, timeout=15)
        server.starttls()
        log_email_diagnostic("SMTP_CONNECT", "SUCCESS", "Connected securely via Port 587 (STARTTLS)!")
        return server
    except Exception as e587:
        log_email_diagnostic("SMTP_CONNECT", "FALLBACK", f"Port 587 failed ({e587}). Trying direct IPv4 {ipv4_address}:465...")

    # Strategy C: Try direct IPv4 address on Port 465
    try:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(ipv4_address, 465, context=context, timeout=15)
        log_email_diagnostic("SMTP_CONNECT", "SUCCESS", f"Connected via direct IPv4 {ipv4_address}:465!")
        return server
    except Exception as e_ip:
        log_email_diagnostic("SMTP_CONNECT", "FAILED", f"All connection strategies failed: {e_ip}")
        raise e_ip

def send_session_email_report(session_data: dict, recipient: str = None) -> tuple[bool, str]:
    """Sends session summary and Excel report via SMTP to the teacher with full step-by-step diagnostic tracing."""
    target_email = recipient or TEACHER_REPORT_EMAIL
    session_id = session_data.get("id", "LIVE_SESSION")
    attendees = session_data.get("attendees", [])
    duration = session_data.get("duration_minutes", 50)
    
    log_email_diagnostic("DISPATCH_TRIGGER", "START", f"Initiating email dispatch for session '{session_id}' (Total Attendees: {len(attendees)}, Recipient: {target_email})")
    
    # 1. Step: Check Credentials
    has_email = bool(SMTP_EMAIL and SMTP_EMAIL.strip())
    has_pass = bool(SMTP_PASSWORD and SMTP_PASSWORD.strip())
    
    log_email_diagnostic(
        "ENV_CONFIG_CHECK", 
        "CHECK", 
        f"SMTP_SERVER='{SMTP_SERVER}', SMTP_EMAIL={'CONFIGURED (' + SMTP_EMAIL + ')' if has_email else 'MISSING / EMPTY'}, SMTP_PASSWORD={'CONFIGURED (LENGTH ' + str(len(SMTP_PASSWORD)) + ')' if has_pass else 'MISSING / EMPTY'}"
    )
    
    report_path = generate_session_excel(session_data)
    log_email_diagnostic("REPORT_GENERATION", "SUCCESS", f"Generated workbook at '{report_path}'")
    
    if not has_email or not has_pass:
        error_explanation = (
            "🚨 CRITICAL EMAIL CONFIGURATION ERROR: "
            "SMTP_EMAIL or SMTP_PASSWORD environment variable is empty! "
            "To fix: Open Hugging Face Settings -> Variables and secrets -> Add 'SMTP_EMAIL' and 'SMTP_PASSWORD'."
        )
        log_email_diagnostic("CREDENTIAL_VALIDATION", "FAILED", error_explanation)
        return False, error_explanation

    try:
        # 2. Step: Build MIME Message
        log_email_diagnostic("MIME_BUILD", "IN_PROGRESS", "Compiling HTML body and embedding student snapshots...")
        msg = MIMEMultipart("related")
        msg["From"] = f"Nexus AI Attendance <{SMTP_EMAIL}>"
        msg["To"] = target_email
        msg["Subject"] = f"📊 Attendance Session Report [{session_id}] - {len(attendees)} Present"
        
        table_rows = ""
        for idx, att in enumerate(attendees, 1):
            table_rows += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px; text-align: center; color: #64748b;">{idx}</td>
                <td style="padding: 10px; font-weight: bold; color: #0284c7;">{att.get('roll_number', 'N/A')}</td>
                <td style="padding: 10px; font-weight: 600; color: #1e293b;">{att.get('name', 'Unknown')}</td>
                <td style="padding: 10px; text-align: center; color: #475569;">{att.get('time', '')}</td>
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
                    <p style="margin: 6px 0 0 0; opacity: 0.85; font-size: 13px;">Session Summary & Verification Ledger</p>
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
                    
                    <h3 style="font-size: 15px; margin-bottom: 12px; color: #334155;">Verified Attendance Ledger</h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; color: #475569; text-transform: uppercase; font-size: 11px;">
                                <th style="padding: 10px; text-align: center;">S.No</th>
                                <th style="padding: 10px; text-align: left;">Roll No</th>
                                <th style="padding: 10px; text-align: left;">Student Name</th>
                                <th style="padding: 10px; text-align: center;">Time</th>
                                <th style="padding: 10px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                    
                    <p style="margin-top: 25px; font-size: 12px; color: #64748b; line-height: 1.5;">
                        📎 The full Excel report file is attached to this email along with student biometric verification snapshots.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg_body = MIMEText(html_content, "html")
        msg.attach(msg_body)
        
        # Attach Excel file
        if os.path.exists(report_path):
            with open(report_path, "rb") as f:
                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            base_filename = os.path.basename(report_path)
            attachment.add_header("Content-Disposition", f"attachment; filename={base_filename}")
            msg.attach(attachment)
            
        # Attach student photos
        attached_photos_count = 0
        for att in attendees:
            photo_rel = att.get("photo")
            if photo_rel and photo_rel.startswith("/"):
                photo_local = photo_rel[1:]
                if os.path.exists(photo_local):
                    try:
                        with open(photo_local, "rb") as img_file:
                            img_data = img_file.read()
                            img_part = MIMEImage(img_data)
                            img_part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(photo_local)}")
                            msg.attach(img_part)
                            attached_photos_count += 1
                    except Exception as e:
                        log_email_diagnostic("PHOTO_ATTACH", "WARNING", f"Could not attach {photo_local}: {e}")

        log_email_diagnostic("MIME_BUILD", "SUCCESS", f"MIME message ready (Excel + {attached_photos_count} student photos attached)")

        # 3. Step: Connect to SMTP Server with Resilient Strategy (IPv4 / Port 465 SSL / Port 587 TLS)
        server = get_smtp_connection()
        
        # 4. Step: Authenticate
        log_email_diagnostic("SMTP_AUTH", "AUTHENTICATING", f"Authenticating as '{SMTP_EMAIL}'...")
        # Clean password (remove spaces in app password if any)
        clean_password = SMTP_PASSWORD.replace(" ", "").strip()
        server.login(SMTP_EMAIL.strip(), clean_password)
        log_email_diagnostic("SMTP_AUTH", "SUCCESS", "Google SMTP Authentication Granted!")

        # 5. Step: Send Message
        log_email_diagnostic("SMTP_SEND", "DISPATCHING", f"Transmitting message to recipient '{target_email}'...")
        server.send_message(msg)
        server.quit()
        
        success_msg = f"✅ EMAIL DELIVERED SUCCESSFULLY to {target_email} with report {os.path.basename(report_path)}"
        log_email_diagnostic("EMAIL_PIPELINE", "SUCCESS", success_msg)
        return True, success_msg

    except smtplib.SMTPAuthenticationError as auth_err:
        err_msg = f"Google SMTP Authentication Rejected (Code {auth_err.smtp_code}): Check your 16-character App Password."
        log_email_diagnostic("SMTP_AUTH", "FAILED", err_msg)
        return False, err_msg
    except Exception as e:
        full_trace = traceback.format_exc()
        err_msg = f"Unexpected SMTP failure: {e}\n{full_trace}"
        log_email_diagnostic("EMAIL_PIPELINE", "CRITICAL_ERROR", err_msg)
        return False, err_msg
