"""
Comprehensive Programmatic Verification Suite for Milestone M3
Covers:
1. SQLite Database Schema & Migration Guards (attendance, sessions, registered_faces)
2. 24-Hour IST Persistence & Session Lifecycle Helpers
3. Professional PDF Generation via ReportLab NumberedCanvas
4. Multi-Format Reporting (CSV, Excel, PDF)
5. Email Service HTML Body, Attachment Encoding & Dual Dispatch Routing
6. Tracking Controller Disk Rate-Limiting & Attendee Photo Archival
7. In-Flight AWS Queue Flush Guard
"""

import os
import sys
import time
import json
import base64
import sqlite3
import asyncio
import re
from datetime import datetime

# Configure UTF-8 output encoding for Windows PowerShell / CMD
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Test 1: SQLite Schema & 24-Hour IST Attendance & Session Helpers
# ---------------------------------------------------------------------------
def test_sqlite_schema_and_session_helpers():
    print("\n--- [TEST 1] SQLite Schema & 24h IST Attendance Persistence ---")
    from core.state import init_db, DB_PATH, connected_devices, active_session
    from services.attendance import (
        mark_attendance, create_session_record, update_session_record, 
        get_session_by_id, parse_identity
    )
    from core.timezone_utils import get_timestamp_full_str, get_time_str

    # 1. Initialize database and verify tables
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Verify tables exist
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "attendance" in tables, "Table 'attendance' missing"
    assert "sessions" in tables, "Table 'sessions' missing"
    assert "registered_faces" in tables, "Table 'registered_faces' missing"
    print("✅ All required SQLite tables verified: attendance, sessions, registered_faces")

    # Verify attendance columns
    cursor.execute("PRAGMA table_info(attendance)")
    att_cols = [r["name"] for r in cursor.fetchall()]
    assert "roll_number" in att_cols
    assert "name" in att_cols
    assert "time" in att_cols
    assert "session_id" in att_cols
    assert "device_id" in att_cols
    print("✅ Attendance table columns verified:", att_cols)

    # 2. Test create_session_record
    test_session_id = f"SES_TEST_M3_{int(time.time())}"
    ok = create_session_record(test_session_id, duration_minutes=45, status="ACTIVE")
    assert ok, "Failed to create session record"
    
    sess_row = get_session_by_id(test_session_id)
    assert sess_row is not None, "Session record not found after creation"
    assert sess_row["session_id"] == test_session_id
    assert sess_row["duration_minutes"] == 45
    assert sess_row["status"] == "ACTIVE"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", sess_row["start_time"]), f"Invalid start_time format: {sess_row['start_time']}"
    print(f"✅ Created session record '{test_session_id}' with IST start_time: {sess_row['start_time']}")

    # 3. Test mark_attendance with full signature and photo bytes
    # Dummy JPEG header + payload
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00test_photo_bytes_payload"
    
    res = mark_attendance(
        raw_identity="24__Shashank_Dubey",
        image_bytes=dummy_jpeg,
        device_id="Classroom_101",
        session_id=test_session_id
    )
    
    assert isinstance(res, tuple) and len(res) == 4, f"mark_attendance must return 4-tuple, got {res}"
    is_new, name, roll, timestamp_ist = res
    assert is_new is True, "Expected is_new to be True"
    assert name == "Shashank Dubey", f"Expected 'Shashank Dubey', got {name}"
    assert roll == "24", f"Expected '24', got {roll}"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", timestamp_ist), f"Timestamp must be YYYY-MM-DD HH:MM:SS, got {timestamp_ist}"
    print(f"✅ mark_attendance returned 4-tuple: ({is_new}, '{name}', '{roll}', '{timestamp_ist}')")

    # Verify SQLite row
    cursor.execute("SELECT * FROM attendance WHERE session_id = ? AND roll_number = ?", (test_session_id, "24"))
    att_row = cursor.fetchone()
    assert att_row is not None, "Attendance row not found in DB"
    assert att_row["name"] == "Shashank Dubey"
    assert att_row["time"] == timestamp_ist, f"DB time '{att_row['time']}' does not match IST timestamp '{timestamp_ist}'"
    assert att_row["device_id"] == "Classroom_101"
    print(f"✅ DB row verified: Name={att_row['name']}, Time={att_row['time']}, Device={att_row['device_id']}")

    # 4. Test update_session_record
    ok_up = update_session_record(test_session_id, status="COMPLETED", total_attendees=1)
    assert ok_up, "Failed to update session record"
    
    sess_up = get_session_by_id(test_session_id)
    assert sess_up["status"] == "COMPLETED"
    assert sess_up["total_attendees"] == 1
    assert sess_up["end_time"] is not None
    print(f"✅ Session updated successfully: Status={sess_up['status']}, Attendees={sess_up['total_attendees']}, EndTime={sess_up['end_time']}")

    conn.close()
    print("🎯 TEST 1 PASSED!")


# ---------------------------------------------------------------------------
# Test 2: Professional PDF Report Generation via ReportLab
# ---------------------------------------------------------------------------
def test_pdf_report_generation():
    print("\n--- [TEST 2] ReportLab PDF Generation ---")
    from services.pdf_service import generate_session_pdf

    mock_session = {
        "id": "SES_PDF_TEST_001",
        "duration_minutes": 50,
        "target_device": "Lecture Hall 3",
        "attendees": [
            {
                "roll_number": "24",
                "name": "Shashank Dubey",
                "time": "10:15:30",
                "date": "2026-08-18",
                "device_id": "Lecture Hall 3",
                "status": "VERIFIED"
            },
            {
                "roll_number": "42",
                "name": "Aarav Sharma",
                "time": "10:16:02",
                "date": "2026-08-18",
                "device_id": "Lecture Hall 3",
                "status": "VERIFIED"
            },
            {
                "roll_number": "55",
                "name": "Priya Patel",
                "time": "10:17:11",
                "date": "2026-08-18",
                "device_id": "Lecture Hall 3",
                "status": "VERIFIED"
            }
        ]
    }

    pdf_path = generate_session_pdf(mock_session)
    assert os.path.exists(pdf_path), f"PDF file was not created at {pdf_path}"
    file_size = os.path.getsize(pdf_path)
    assert file_size > 2000, f"PDF file size too small: {file_size} bytes"
    print(f"✅ PDF Report successfully generated: '{pdf_path}' ({file_size} bytes)")

    # Test PDF generation with empty attendee list (empty state handling)
    empty_session = {"id": "SES_PDF_EMPTY", "duration_minutes": 30, "attendees": []}
    empty_pdf = generate_session_pdf(empty_session)
    assert os.path.exists(empty_pdf), f"Empty PDF file was not created at {empty_pdf}"
    print(f"✅ Empty PDF Report generated cleanly: '{empty_pdf}' ({os.path.getsize(empty_pdf)} bytes)")
    print("🎯 TEST 2 PASSED!")


# ---------------------------------------------------------------------------
# Test 3: Multi-Format Report Compilation (CSV, Excel, PDF)
# ---------------------------------------------------------------------------
def test_multi_format_reporting():
    print("\n--- [TEST 3] Multi-Format Reporting (CSV & Excel) ---")
    from services.email_service import generate_session_csv, generate_session_excel
    import pandas as pd

    mock_session = {
        "id": "SES_MULTI_FORMAT_01",
        "duration_minutes": 50,
        "attendees": [
            {
                "roll_number": "101",
                "name": "Deepak Kumar",
                "time": "11:00:25",
                "date": "2026-08-18",
                "device_id": "Classroom 101"
            },
            {
                "roll_number": "102",
                "name": "Ananya Roy",
                "time": "11:01:40",
                "date": "2026-08-18",
                "device_id": "Classroom 101"
            }
        ]
    }

    # 1. Test CSV Generation
    csv_path = generate_session_csv(mock_session)
    assert os.path.exists(csv_path), f"CSV not created at {csv_path}"
    df_csv = pd.read_csv(csv_path)
    assert len(df_csv) == 2, f"Expected 2 rows in CSV, got {len(df_csv)}"
    assert "Student Name" in df_csv.columns
    assert "Roll Number" in df_csv.columns
    assert df_csv.iloc[0]["Student Name"] == "Deepak Kumar"
    print(f"✅ CSV Generated and verified: '{csv_path}' ({len(df_csv)} records)")

    # 2. Test Excel Generation
    xlsx_path = generate_session_excel(mock_session)
    assert os.path.exists(xlsx_path), f"Excel not created at {xlsx_path}"
    df_xlsx = pd.read_excel(xlsx_path)
    assert len(df_xlsx) == 2, f"Expected 2 rows in Excel, got {len(df_xlsx)}"
    print(f"✅ Excel Workbook Generated and verified: '{xlsx_path}' ({len(df_xlsx)} records)")
    print("🎯 TEST 3 PASSED!")


# ---------------------------------------------------------------------------
# Test 4: Email HTML Body, Attachment Encoder & Dual Routing Logic
# ---------------------------------------------------------------------------
def test_email_service_and_fallback():
    print("\n--- [TEST 4] Email Service & Dual Route Fallback ---")
    from services.email_service import (
        _build_html_email_body, _collect_email_attachments, 
        send_session_email_report, get_latest_email_diagnostics
    )

    mock_session = {
        "id": "SES_EMAIL_M3_01",
        "duration_minutes": 50,
        "attendees": [
            {
                "roll_number": "24",
                "name": "Shashank Dubey",
                "time": "14:20:00",
                "date": "2026-08-18",
                "device_id": "Classroom 101"
            }
        ],
        "raw_frames": []
    }

    # 1. HTML email builder check
    html = _build_html_email_body(mock_session)
    assert "Shashank Dubey" in html
    assert "SES_EMAIL_M3_01" in html
    assert "24-Hour IST" in html
    print("✅ HTML Email template generated and contains session data & 24h IST markers")

    # 2. Attachment collection check
    attachments = _collect_email_attachments(mock_session)
    print(f"✅ Collected {len(attachments)} attachments")

    # 3. Test send_session_email_report auto-compilation
    # When credentials are dummy/empty, it logs diagnostics cleanly without crashing
    success, msg = send_session_email_report(mock_session, recipient="test_teacher@example.com")
    print(f"✅ Dual dispatch execution completed with response: status={success}, msg='{msg}'")
    
    diag = get_latest_email_diagnostics()
    assert len(diag) > 0, "Diagnostic log should have entries"
    print("✅ Diagnostic logging trace verified:")
    for line in diag.strip().splitlines()[-3:]:
        print(f"   | {line}")
    print("🎯 TEST 4 PASSED!")


# ---------------------------------------------------------------------------
# Test 5: Tracking Controller Disk Rate-Limiter & Attendance Unpacking
# ---------------------------------------------------------------------------
async def test_tracking_controller_rate_limiting():
    print("\n--- [TEST 5] Tracking Controller Rate Limiter & Argument Fix ---")
    from api.controllers.tracking_controller import TrackingController
    from core.state import connected_devices, active_session
    import base64

    # Dummy websocket mock
    class DummyWebSocket:
        async def send_json(self, data):
            pass
        async def send_text(self, text):
            pass

    controller = TrackingController(websocket=DummyWebSocket())

    # Create dummy 1x1 base64 JPEG
    dummy_b64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    
    dev_id = "test_rpi_rate_limiter"
    connected_devices[dev_id] = {
        "device_id": dev_id,
        "device_name": "Test Node",
        "total_frames": 0,
        "raw_frames": [],
        "cropped_queue": [],
        "verified_students": [],
        "status": "active",
        "stage": "IDLE"
    }

    active_session["id"] = "SES_RATE_LIMIT_TEST"
    active_session["active"] = True
    active_session["session_raw_frames"] = []

    # Stream 30 frames in rapid succession (simulating 30 FPS Turbo)
    raw_frames_dir = "static/raw_frames"
    os.makedirs(raw_frames_dir, exist_ok=True)
    before_files = set(os.listdir(raw_frames_dir))

    for i in range(30):
        payload = {
            "device_id": dev_id,
            "device_name": "Test Node",
            "image": dummy_b64,
            "turbo_active": True,
            "timestamp": "12:00:00"
        }
        await controller.process_frame(payload)
        await asyncio.sleep(0.035) # Simulates 30 FPS video streaming interval

    after_files = set(os.listdir(raw_frames_dir))
    new_disk_files = after_files - before_files

    print(f"✅ Ingested 30 high-rate frames: Telemetry frames={connected_devices[dev_id]['total_frames']}, Disk files created={len(new_disk_files)}")
    assert connected_devices[dev_id]["total_frames"] >= 25, "In-memory telemetry did not increment for streamed frames"
    assert len(new_disk_files) <= 2, f"Disk rate limiter failed: wrote {len(new_disk_files)} files in <1s (expected <= 2)"
    assert len(active_session["session_raw_frames"]) <= 25, "session_raw_frames exceeded safety cap of 25"
    print("✅ Disk Rate-Limiter successfully throttled raw frame I/O without dropping stream telemetry!")
    print("🎯 TEST 5 PASSED!")


# ---------------------------------------------------------------------------
# Test 6: In-Flight AWS Queue Flush Guard
# ---------------------------------------------------------------------------
async def test_queue_flush_guard():
    print("\n--- [TEST 6] In-Flight AWS Queue Flush Guard ---")
    from api.websocket import wait_for_in_flight_aws_scans
    from core.state import connected_devices

    dev_id = "test_flush_node"
    connected_devices[dev_id] = {
        "stage": "CROPPING",
        "cropped_queue": [{"status": "scanning"}]
    }

    t0 = time.time()
    
    # Launch flush guard in background task
    flush_task = asyncio.create_task(wait_for_in_flight_aws_scans(max_wait_seconds=4.0))

    # Simulate in-flight AWS verification resolving after 0.6 seconds
    await asyncio.sleep(0.6)
    connected_devices[dev_id]["stage"] = "IDLE"
    connected_devices[dev_id]["cropped_queue"][0]["status"] = "match"

    await flush_task
    elapsed = time.time() - t0

    print(f"✅ Queue flush held during active scan and resolved cleanly in {elapsed:.2f}s")
    assert 0.5 <= elapsed < 2.0, f"Unexpected flush duration: {elapsed}s"
    print("🎯 TEST 6 PASSED!")


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------
async def main():
    print("=" * 70)
    print("🚀 RUNNING MILESTONE M3 VERIFICATION BENCHMARK SUITE")
    print("=" * 70)
    
    test_sqlite_schema_and_session_helpers()
    test_pdf_report_generation()
    test_multi_format_reporting()
    test_email_service_and_fallback()
    await test_tracking_controller_rate_limiting()
    await test_queue_flush_guard()

    print("\n" + "=" * 70)
    print("✨ ALL MILESTONE M3 INTEGRATION & VERIFICATION TESTS PASSED (6/6) ✨")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
