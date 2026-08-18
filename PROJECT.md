# Project: AWS Rekognition Biometric Attendance & Surveillance Platform

## Architecture & System Overview
The AWS Rekognition Biometric Attendance & Surveillance Platform is a multi-tier, high-throughput computer vision and IoT platform integrating:
1. **Edge Surveillance Layer (`rpi_streamer.py`, `setup-pi.sh`)**:
   - Hardware-assisted multi-threaded 30 FPS video streaming with `cv2.CAP_PROP_BUFFERSIZE=1`.
   - Sub-millisecond optical motion differencing ($160 \times 90$ matrix absdiff in $<0.25\text{ms}$).
   - Hardware V4L2 anti-motion-blur shutter priority (`exposure_auto_priority=0`) and SIMD gamma LUT illumination booster ($<0.3\text{ms}$).
   - Universal WebSocket auto-reconnect engine immune to keepalive ping timeouts (`ping_interval=None, ping_timeout=None`).
   - Live telemetry logging: FPS, motion velocity (km/h), Laplacian sharpness score, and CPU temperature.
2. **4K Batch Photo Crowd Recognition Layer (`services/face_detector.py`, `services/fast_nms.cpp`)**:
   - Pyramidal multi-scale SAHI slicing engine for ultra-high-resolution 4K ($3840 \times 2160$) photos isolating 200+ small/distant faces.
   - 3-tier pyramidal slicing: Tier 1 Global ($640 \times 640$), Tier 2 Mid-Grid ($640 \times 640$, step 480 / 25% overlap, 40 tiles), Tier 3 Micro-Grid ($480 \times 480$, step 360 / 25% overlap, 66 tiles) + Test-Time Augmentation (TTA).
   - High-performance C++ C-ABI NMS engine (`fast_nms_c` / `fast_soft_nms_c`) executing in $<1\text{ms}$ ($N=5,000$) and $<5\text{ms}$ ($N=50,000$) with vectorized NumPy fallback.
   - Normalized face crops with 22% horizontal / 26% vertical margin expansion, unsharp masking ($1.45 \cdot I - 0.45 \cdot \text{Gaussian}$) for sub-140px crops, and sanitized `ExternalImageId`.
3. **Enterprise Attendance Workflow & Reporting Layer (`api/`, `services/`, `core/`)**:
   - Central server tracking controller managing multi-device classroom monitoring sessions with roll number + student name.
   - In-flight AWS Rekognition queue flush guard (`wait_for_in_flight_aws_scans`) during session termination.
   - Persistent SQLite database schema with 24-hour IST timestamps (`Asia/Kolkata`) and `sessions` tracking.
   - Real-time WebSocket dashboard broadcast of session state, attendee list, telemetry, and camera status.
   - Automated multi-format reporting: styled Excel (`.xlsx`), standard CSV (`.csv`), and PDF (`.pdf`) delivery with SMTP/Resend email dispatch.
4. **Automated Comprehensive Verification Benchmark Suite (`tests/`)**:
   - Standalone programmatic test suite covering Tiers 1-4: 4K synthetic crowd detection (200+ faces), sub-5ms C++ NMS latency/IoU, multi-device WebSocket concurrency (30+ clients) at 30 FPS Turbo streaming with 0 ping timeouts, E2E SQLite/CSV persistence in 24h IST, and in-flight AWS queue flush guard.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Multi-Threaded 30 FPS Stream | Background hardware polling thread with zero frame lag | M1 | R1 Spec |
| 2 | Sub-ms Optical Differencing | $160 \times 90$ downsampled absdiff in $<0.25\text{ms}$ | M1 | R1 Spec |
| 3 | Hardware Anti-Blur Shutter Priority | V4L2 `exposure_auto_priority=0` + SIMD gamma LUT booster | M1 | R1 Spec |
| 4 | Resilient WebSocket Engine | Auto-reconnect with `ping_interval=None, ping_timeout=None` | M1 | R1 Spec |
| 5 | Edge Live Telemetry Logging | Terminal display of live FPS, velocity (km/h), sharpness, CPU temp | M1 | R1 Spec |
| 6 | Fast Motion Capture (10-15 km/h) | Sharp face capture under rapid subject movement | M1 | R1 Spec |
| 7 | Pyramidal 3-Tier SAHI Slicing | Global, 640x640, and 480x480 micro-grid slicing for 4K frames | M2 | R2 Spec |
| 8 | 200+ Crowd Face Isolation | Detects and crops 200+ faces in high-density 4K images | M2 | R2 Spec |
| 9 | Sub-5ms C++ NMS Engine | Compiled C++ C-ABI DLL (`fast_nms.dll`) with vectorized fallback | M2 | R2 Spec |
| 10 | Normalized Face Cropping | 22% H / 26% V expansion + unsharp masking for AWS Rekognition | M2 | R2 Spec |
| 11 | Central Server Session Controller | Multi-device tracking, start/stop/duration session controller | M3 | R3 Spec |
| 12 | SQLite 24h IST Persistence | DB attendance & sessions records with explicit 24h IST timestamps | M3 | R3 Spec |
| 13 | In-Flight AWS Queue Flush Guard | Prevents lost attendance records during session auto-stop/manual stop | M3 | R3 Spec |
| 14 | Real-Time WebSocket Broadcast | Instantaneous UI updates for session status, attendees, and metrics | M3 | R3 Spec |
| 15 | Multi-Format Automated Reporting | Formatted Excel (.xlsx), CSV (.csv), and PDF (.pdf) reports via SMTP | M3 | R3 Spec |
| 16 | 4K Crowd Benchmark Test | Benchmark 200+ face detection accuracy on synthetic 4K images | M4 | R4 Spec |
| 17 | NMS Latency Benchmark Test | Verify sub-5ms execution on large bounding box candidate sets | M4 | R4 Spec |
| 18 | Multi-Device Concurrency Test | Test 30+ concurrent WebSocket edge streamers with 0 ping timeouts | M4 | R4 Spec |
| 19 | E2E Attendance Verification Test | Validate end-to-end flow from frame to SQLite persistence in 24h IST | M4 | R4 Spec |
| 20 | In-Flight Queue Flush Test | Verify zero dropped attendees during session conclusion | M4 | R4 Spec |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Resilient Multi-Device Edge Surveillance (R1) | `rpi_streamer.py`, `setup-pi.sh`, multi-threaded 30 FPS capture, optical motion differencing, anti-blur shutter priority, WebSocket auto-reconnect, telemetry logs | None | PLANNED |
| M2 | 4K Batch Crowd Recognition & Fast NMS (R2) | `services/face_detector.py`, `services/fast_nms.cpp`, `services/fast_nms.py`, 3-tier pyramidal SAHI slicing, compiled C++ NMS DLL, crop normalization, AWS matching | None | PLANNED |
| M3 | Enterprise Attendance Workflow & Reporting (R3) | `api/controllers/tracking_controller.py`, `api/websocket.py`, `services/attendance.py`, `core/state.py`, `services/pdf_service.py`, `services/email_service.py`, SQLite schema & 24h IST timestamps, in-flight queue flush, PDF/CSV/Excel/SMTP delivery | None | PLANNED |
| M4 | Automated Benchmark & Verification Suite (R4 & E2E Track) | `tests/test_benchmark_suite.py`, `tests/mock_aws_rekognition.py`, `tests/test_infra.py`, Tiers 1-4 comprehensive automated verification | M1, M2, M3 | PLANNED |
| Final | 100% E2E Pass, Adversarial Hardening & Forensic Audit | Run full test suite across Tiers 1-4, execute Tier 5 Challenger stress harness, complete Forensic Integrity Audit | M1, M2, M3, M4 | PLANNED |

---

## Code Layout
```
aws_rekognition_project/
├── api/
│   ├── __init__.py
│   ├── auth.py
│   ├── websocket.py                  # WebSocket broadcasting & session management
│   └── controllers/
│       ├── __init__.py
│       ├── event_controller.py       # 4K Batch photo processing endpoint
│       └── tracking_controller.py    # Edge streaming & best-shot ingestion
├── core/
│   ├── __init__.py
│   ├── config.py                     # App configuration & credentials
│   └── state.py                      # Global state & SQLite connection initialization
├── faces_db/
│   └── system.db                     # SQLite database (attendance, registered_faces, sessions)
├── models/
│   └── scrfd_2.5g_bnkps.onnx          # Face detection ONNX weights
├── reports/                          # Generated Excel, CSV, and PDF reports
├── services/
│   ├── __init__.py
│   ├── attendance.py                 # Attendance marking & SQLite persistence (24h IST)
│   ├── aws_client.py                 # AWS Rekognition client wrapper
│   ├── email_service.py              # Email dispatch (SMTP & Resend) & Excel/CSV export
│   ├── face_detector.py              # 3-Tier Pyramidal SAHI Face Detector
│   ├── fast_nms.cpp                  # Sub-5ms C++ NMS / Soft-NMS C-ABI implementation
│   ├── fast_nms.py                   # Ctypes loader & vectorized NumPy fallback
│   ├── liveness.py                   # MediaPipe anti-spoofing liveness verification
│   └── pdf_service.py                # Automated PDF report generator
├── static/
│   ├── app.js                        # Frontend UI logic
│   ├── index.html                    # Dashboard UI
│   └── attendee_crops/               # Attendee face thumbnails
├── tests/
│   ├── __init__.py
│   ├── mock_aws_rekognition.py       # Mock AWS client for deterministic CI testing
│   ├── test_benchmark_suite.py       # Complete R4 automated verification suite
│   └── test_infra.py                 # Test runner & reporting harness
├── rpi_streamer.py                   # Edge camera daemon (30 FPS, anti-blur, telemetry)
├── setup-pi.sh                       # Raspberry Pi provisioning script
├── main.py                           # FastAPI application entrypoint
├── PROJECT.md                        # Master project architecture & milestone tracker
├── TEST_INFRA.md                     # E2E Test Suite design & feature coverage matrix
└── TEST_READY.md                     # Test Suite completion publication
```

---

## Interface Contracts

### Edge Streamer (`rpi_streamer.py`) ↔ Server (`api/websocket.py` & `api/controllers/tracking_controller.py`)
- **WebSocket Protocol**: `ws://<host>:<port>/ws/stream/{device_id}`
- **Registration Message**: `{"type": "register", "device_id": str, "device_name": str, "mode": "stream"}`
- **Frame Ingestion**: Binary JPEG frames sent over WebSocket or Best-Shot payload `{"type": "best_shot", "frame_jpg": base64_str, "sharpness": float, "velocity": float}`
- **Command Messages (Server -> Edge)**: `{"command": "start_session", "session_id": str, "duration": int}` / `{"command": "stop_session"}`

### 4K SAHI Face Detector ↔ AWS Rekognition Client (`services/face_detector.py` ↔ `services/aws_client.py`)
- **Input**: High-resolution image (NumPy array BGR `(H, W, 3)`), `score_threshold: float = 0.4`, `nms_threshold: float = 0.45`
- **Output**: `bboxes`: `np.ndarray` `(N, 4)` `[x1, y1, x2, y2]`, `kpss`: `np.ndarray` `(N, 5, 2)` landmark coordinates, `scores`: `np.ndarray` `(N,)`
- **Crop Generator**: `extract_normalized_face_crops(image, bboxes)` -> `List[Tuple[bytes, Tuple[int, int, int, int]]]`

### Session Controller ↔ SQLite Attendance Service (`api/controllers/tracking_controller.py` ↔ `services/attendance.py`)
- **Function Signature**: `mark_attendance(raw_identity: str, image_bytes: bytes = None, device_id: str = "edge_device", session_id: str = None) -> Tuple[bool, str, str, str]`
- **Return Tuple**: `(is_new_marked: bool, student_name: str, roll_number: str, timestamp_ist_str: str)`
- **SQLite Write**: Explicit insertion of 24h IST formatted string (`YYYY-MM-DD HH:MM:SS`) into `time` column.

### Session Conclusion ↔ Multi-Format Reporting (`api/websocket.py` ↔ `services/email_service.py` & `services/pdf_service.py`)
- **Queue Flush**: `await wait_for_in_flight_aws_scans(max_wait_seconds=6.0)` before consolidating attendees.
- **Reporting Generator**:
  - `generate_session_excel(session_id, attendees) -> str` (filepath `.xlsx`)
  - `generate_session_csv(session_id, attendees) -> str` (filepath `.csv`)
  - `generate_session_pdf(session_id, attendees) -> str` (filepath `.pdf`)
- **Email Delivery**: `send_session_email_report(to_email, session_id, attendees, attachment_paths)` with SMTP and Resend fallback.
