# E2E Test Infra: AWS Rekognition Biometric Attendance & Surveillance Platform

## Test Philosophy
- **Opaque-Box & Requirement-Driven**: Tests are derived strictly from `ORIGINAL_REQUEST.md` and user-facing acceptance criteria, independent of internal module implementation quirks.
- **Systematic 4-Tier Test Methodology**:
  1. **Tier 1 - Feature Coverage (>=5 per feature)**: Unit and isolated integration tests for each individual feature.
  2. **Tier 2 - Boundary & Corner Cases (>=5 per feature)**: Extreme resolutions, 0-face images, 200+ dense crowds, high motion velocities, network dropouts, empty DB queries, UTC vs IST timezone edges.
  3. **Tier 3 - Cross-Feature Combinations (Pairwise Coverage)**: Turbo 30 FPS streaming concurrent with active 4K batch processing and automated session stop triggers.
  4. **Tier 4 - Real-World Application Scenarios**: Multi-camera classroom attendance simulations (30+ concurrent WebSocket streams, 200+ attendees, queue flush guard, multi-format report generation, and SMTP verification).
  5. **Tier 5 - Adversarial Coverage Hardening**: White-box stress testing, memory leak detection, extreme contention, and fuzzing.

---

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|-------------|:------:|:------:|:------:|:------:|
| 1 | Multi-Threaded 30 FPS Stream | R1 | 5 | 5 | ✓ | ✓ |
| 2 | Sub-ms Optical Differencing | R1 | 5 | 5 | ✓ | ✓ |
| 3 | Hardware Anti-Blur Shutter Priority | R1 | 5 | 5 | ✓ | ✓ |
| 4 | Resilient WebSocket Auto-Reconnect | R1 | 5 | 5 | ✓ | ✓ |
| 5 | Edge Live Telemetry Logging | R1 | 5 | 5 | ✓ | ✓ |
| 6 | Fast Motion Capture (10-15 km/h) | R1 | 5 | 5 | ✓ | ✓ |
| 7 | Pyramidal 3-Tier SAHI Slicing | R2 | 5 | 5 | ✓ | ✓ |
| 8 | 200+ Crowd Face Isolation | R2 | 5 | 5 | ✓ | ✓ |
| 9 | Sub-5ms C++ NMS Engine | R2 | 5 | 5 | ✓ | ✓ |
| 10 | Normalized Face Cropping | R2 | 5 | 5 | ✓ | ✓ |
| 11 | Central Server Session Controller | R3 | 5 | 5 | ✓ | ✓ |
| 12 | SQLite 24h IST Persistence | R3 | 5 | 5 | ✓ | ✓ |
| 13 | In-Flight AWS Queue Flush Guard | R3 | 5 | 5 | ✓ | ✓ |
| 14 | Real-Time WebSocket Broadcast | R3 | 5 | 5 | ✓ | ✓ |
| 15 | Multi-Format Automated Reporting | R3 | 5 | 5 | ✓ | ✓ |
| 16 | 4K Crowd Benchmark Test | R4 | 5 | 5 | ✓ | ✓ |
| 17 | NMS Latency Benchmark Test | R4 | 5 | 5 | ✓ | ✓ |
| 18 | Multi-Device Concurrency Test | R4 | 5 | 5 | ✓ | ✓ |
| 19 | E2E Attendance Verification Test | R4 | 5 | 5 | ✓ | ✓ |
| 20 | In-Flight Queue Flush Test | R4 | 5 | 5 | ✓ | ✓ |

---

## Test Architecture & Runner
- **Runner Script**: `tests/test_benchmark_suite.py` and `tests/test_infra.py`
- **Invocation Command**: `python -m unittest discover -s tests -p "test_*.py"` or `python tests/test_benchmark_suite.py`
- **Offline / Deterministic Mock Mode**: `tests/mock_aws_rekognition.py` provides deterministic AWS Rekognition collection responses when testing without live cloud credentials.

---

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Multi-Device Edge Classroom Session (30+ nodes streaming @ 30 FPS with motion trigger) | F1, F2, F3, F4, F5, F11, F14 | High |
| 2 | High-Density 4K Auditorium Photo Batch Attendance (200+ faces in single 4K image) | F7, F8, F9, F10, F12, F15 | High |
| 3 | Session Termination with Active In-Flight Scans (Queue Flush Guard + Multi-format Reports) | F11, F12, F13, F14, F15 | High |
| 4 | Rapid Motion Shutter Freeze & Face Crop Verification (Simulated 12 km/h face movement) | F1, F2, F3, F6, F10, F12 | Medium |
| 5 | Network Failure & Rapid Reconnection Recovery during Active Session | F4, F5, F11, F14 | Medium |

---

## Coverage Thresholds
- **Tier 1**: ≥ 5 tests per feature (≥ 100 tests)
- **Tier 2**: ≥ 5 boundary/corner tests per feature (≥ 100 tests)
- **Tier 3**: Pairwise coverage of all major feature interactions (≥ 20 combination tests)
- **Tier 4**: ≥ 5 realistic end-to-end application scenarios
- **Total Minimum Test Count**: ≥ 225 test cases across the suite.
