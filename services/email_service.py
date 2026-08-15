import os
import smtplib
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
        # Try writing to Excel (.xlsx)
        df.to_excel(filepath, index=False, sheet_name="Attendance_Session")
    except Exception as e:
        # Fallback to CSV if openpyxl engine is missing
        csv_filename = f"Attendance_Report_{session_id}_{timestamp}.csv"
        filepath = os.path.join(REPORTS_DIR, csv_filename)
        df.to_csv(filepath, index=False)
        print(f"ℹ️ Saved as CSV ({filepath}) due to: {e}")
        
    return filepath

def send_session_email_report(session_data: dict, recipient: str = None) -> tuple[bool, str]:
    """Sends session summary and Excel report via SMTP to the teacher."""
    target_email = recipient or TEACHER_REPORT_EMAIL
    
    # Generate the report file
    report_path = generate_session_excel(session_data)
    attendees = session_data.get("attendees", [])
    session_id = session_data.get("id", "LIVE_SESSION")
    start_time = session_data.get("start_time", "N/A")
    duration = session_data.get("duration_minutes", 50)
    
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        msg = f"Report saved locally to {report_path}. (SMTP credentials not configured in .env. Target recipient: {target_email})"
        print(f"⚠️ {msg}")
        return False, msg

    try:
        msg = MIMEMultipart("related")
        msg["From"] = f"Nexus AI Attendance <{SMTP_EMAIL}>"
        msg["To"] = target_email
        msg["Subject"] = f"📊 Attendance Session Report [{session_id}] - {len(attendees)} Present"
        
        # Build HTML Email Body
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
        
        # Attach the Excel / CSV file
        if os.path.exists(report_path):
            with open(report_path, "rb") as f:
                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            base_filename = os.path.basename(report_path)
            attachment.add_header("Content-Disposition", f"attachment; filename={base_filename}")
            msg.attach(attachment)
            
        # Attach all student verification snapshots
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
                    except Exception as e:
                        print(f"⚠️ Error attaching image {photo_local}: {e}")

        # Connect to SMTP Server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Successfully dispatched session report email to {target_email}")
        return True, f"Email successfully sent to {target_email} with report {os.path.basename(report_path)}"

    except Exception as e:
        err_msg = f"Failed to send email: {e}"
        print(f"🔴 SMTP Error: {err_msg}")
        return False, err_msg
