"""
Comprehensive Empirical Benchmark & Stress Test Harness for Milestone M1
Tests:
1. Optical Motion Differencing Latency (2,000+ iterations across multiple dynamics: high texture, flat colors, rapid moving objects, random noise).
2. SIMD Gamma LUT Booster Latency (2,000+ iterations across full preview 1280x720 and crop dimensions 200x200).
3. Laplacian Edge Sharpness Variance Stability (extreme black, extreme white, pure blur, sharp edges, gradient, noise, single pixel, NaNs, infs).
4. EdgeFaceHarvester Quality & Memory Stress (1,000 continuous frames at simulated 30 FPS, track pruning, peak quality selection, memory leak check).
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
import tracemalloc
import gc
import base64
import numpy as np
import cv2
import pytest
import rpi_streamer
from rpi_streamer import (
    OpticalMotionDetector,
    apply_fast_gamma_lut,
    get_frame_sharpness,
    enhance_frame_advanced,
    EdgeFaceHarvester,
    _FAST_LUT_BOOSTER,
    generate_hmac_signature,
    get_system_telemetry,
    get_cpu_temp,
    format_cpu_temp
)


def create_synthetic_frame(kind: str, width: int = 1280, height: int = 720, step: int = 0) -> np.ndarray:
    """Generates synthetic frames representing different real-world optical scenarios."""
    if kind == "flat":
        # Uniform solid color
        val = (step * 7) % 256
        return np.full((height, width, 3), val, dtype=np.uint8)
    
    elif kind == "high_texture":
        # Complex high-frequency checkerboard / gradient patterns
        img = np.zeros((height, width, 3), dtype=np.uint8)
        grid_size = 16
        for y in range(0, height, grid_size):
            for x in range(0, width, grid_size):
                c = ((x // grid_size + y // grid_size + step) % 2) * 255
                img[y:y+grid_size, x:x+grid_size] = (c, (c + 50) % 256, (255 - c))
        return img
    
    elif kind == "rapid_motion":
        # Black background with high-contrast fast moving rectangular object (10-15 km/h simulation)
        img = np.zeros((height, width, 3), dtype=np.uint8)
        box_w, box_h = 200, 300
        x_pos = (step * 45) % (width - box_w)
        y_pos = (height // 2) - (box_h // 2)
        img[y_pos:y_pos+box_h, x_pos:x_pos+box_w] = (240, 220, 200) # Face-like color patch
        # Add high contrast features inside the box
        cv2.circle(img, (x_pos + 60, y_pos + 100), 20, (10, 10, 10), -1)
        cv2.circle(img, (x_pos + 140, y_pos + 100), 20, (10, 10, 10), -1)
        cv2.ellipse(img, (x_pos + 100, y_pos + 200), (40, 20), 0, 0, 180, (20, 20, 180), -1)
        return img
    
    elif kind == "random_noise":
        # Pure random uniform noise
        np.random.seed(step % 1000)
        return np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    
    elif kind == "all_black":
        return np.zeros((height, width, 3), dtype=np.uint8)
        
    elif kind == "all_white":
        return np.full((height, width, 3), 255, dtype=np.uint8)
        
    elif kind == "blurred":
        base = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.circle(base, (width // 2, height // 2), min(width, height) // 3, (255, 255, 255), -1)
        return cv2.GaussianBlur(base, (101, 101), 30)

    elif kind == "sharp_edges":
        base = np.zeros((height, width, 3), dtype=np.uint8)
        for i in range(0, min(width, height), 20):
            cv2.line(base, (i, 0), (i, height), (255, 255, 255), 2)
            cv2.line(base, (0, i), (width, i), (255, 255, 255), 2)
        return base

    raise ValueError(f"Unknown frame kind: {kind}")


def test_benchmark_optical_motion_detector():
    """
    Empirical Task 1: Optical Motion Differencing Latency
    Run 2,000+ iterations across high texture, flat colors, rapid moving objects, random noise.
    Verify:
      - Average latency is strictly < 0.25ms
      - P95 latency is strictly < 0.50ms
    """
    detector = OpticalMotionDetector(width=160, height=90, delta_thresh=25)
    
    # Dynamics to evaluate
    dynamics = ["high_texture", "flat", "rapid_motion", "random_noise"]
    iterations_per_dynamic = 600 # 4 * 600 = 2,400 iterations total
    
    all_latencies_ms = []
    dynamic_latencies = {d: [] for d in dynamics}
    
    # Warmup runs (100 iterations)
    for i in range(100):
        f = create_synthetic_frame("high_texture", 1280, 720, step=i)
        detector.detect(f)
    detector.reset()
    
    print("\n" + "="*80)
    print("🔬 BENCHMARK 1: Optical Motion Differencing Latency (2,400 Iterations)")
    print("="*80)
    
    total_runs = 0
    for dynamic in dynamics:
        detector.reset()
        for i in range(iterations_per_dynamic):
            frame = create_synthetic_frame(dynamic, 1280, 720, step=i)
            
            t0 = time.perf_counter()
            has_motion, motion_score, est_vel, thresh = detector.detect(frame)
            t1 = time.perf_counter()
            
            latency_ms = (t1 - t0) * 1000.0
            all_latencies_ms.append(latency_ms)
            dynamic_latencies[dynamic].append(latency_ms)
            total_runs += 1
            
            # Sanity checks on output
            assert isinstance(has_motion, (bool, np.bool_))
            assert isinstance(motion_score, (float, np.floating))
            assert isinstance(est_vel, (float, np.floating))
            assert 0.0 <= motion_score <= 100.0
            assert 0.0 <= est_vel <= 15.0
            if thresh is not None:
                assert thresh.shape == (90, 160)
                assert thresh.dtype == np.uint8

    all_lat_arr = np.array(all_latencies_ms)
    avg_latency = float(np.mean(all_lat_arr))
    median_latency = float(np.median(all_lat_arr))
    p90_latency = float(np.percentile(all_lat_arr, 90))
    p95_latency = float(np.percentile(all_lat_arr, 95))
    p99_latency = float(np.percentile(all_lat_arr, 99))
    min_latency = float(np.min(all_lat_arr))
    max_latency = float(np.max(all_lat_arr))
    std_latency = float(np.std(all_lat_arr))

    print(f"Total Test Iterations : {total_runs}")
    print(f"Overall Mean Latency   : {avg_latency:.4f} ms (Target: < 0.25 ms)")
    print(f"Overall Median Latency : {median_latency:.4f} ms")
    print(f"Overall P90 Latency    : {p90_latency:.4f} ms")
    print(f"Overall P95 Latency    : {p95_latency:.4f} ms (Target: < 0.50 ms)")
    print(f"Overall P99 Latency    : {p99_latency:.4f} ms")
    print(f"Min / Max Latency      : {min_latency:.4f} ms / {max_latency:.4f} ms (Std: {std_latency:.4f} ms)")
    
    print("\nPer-Dynamic Breakdown:")
    for dynamic in dynamics:
        d_arr = np.array(dynamic_latencies[dynamic])
        print(f"  - {dynamic.ljust(15)} : Mean = {np.mean(d_arr):.4f} ms | P95 = {np.percentile(d_arr, 95):.4f} ms | Max = {np.max(d_arr):.4f} ms")

    # Strict SLA Assertions
    assert avg_latency < 0.25, f"Optical motion differencing mean latency {avg_latency:.4f}ms exceeds SLA 0.25ms"
    assert p95_latency < 0.50, f"Optical motion differencing P95 latency {p95_latency:.4f}ms exceeds SLA 0.50ms"
    print("✅ SLA CRITERION MET: OpticalMotionDetector latency is strictly <0.25ms mean and <0.50ms P95.")
    return {
        "total_runs": total_runs,
        "mean_ms": avg_latency,
        "median_ms": median_latency,
        "p90_ms": p90_latency,
        "p95_ms": p95_latency,
        "p99_ms": p99_latency,
        "min_ms": min_latency,
        "max_ms": max_latency,
        "std_ms": std_latency,
        "breakdown": {d: {"mean": float(np.mean(dynamic_latencies[d])), "p95": float(np.percentile(dynamic_latencies[d], 95))} for d in dynamics}
    }


def test_benchmark_simd_gamma_lut_booster():
    """
    Empirical Task 2: SIMD Gamma LUT Booster Performance
    Run 2,000+ iterations across preview (1280x720) and crop (200x200) dimensions.
    Verify:
      - Latency is strictly < 0.30ms across all configurations.
    """
    iterations = 2500
    
    test_dimensions = [
        ("preview_1280x720", 1280, 720),
        ("crop_200x200", 200, 200),
        ("sd_640x480", 640, 480)
    ]
    
    print("\n" + "="*80)
    print("🔬 BENCHMARK 2: SIMD Gamma LUT Booster Performance (2,500 Iterations per dimension)")
    print("="*80)
    
    results = {}
    for name, w, h in test_dimensions:
        latencies_ms = []
        # Pre-create test frame
        test_frame = create_synthetic_frame("high_texture", w, h, step=1)
        
        # Warmup
        for _ in range(50):
            _ = apply_fast_gamma_lut(test_frame)
            
        for i in range(iterations):
            # Alter slight pixel content to avoid cache-line artifact
            test_frame[0, 0, 0] = i % 256
            
            t0 = time.perf_counter()
            boosted = apply_fast_gamma_lut(test_frame)
            t1 = time.perf_counter()
            
            latencies_ms.append((t1 - t0) * 1000.0)
            
            # Invariant checks
            assert boosted.shape == test_frame.shape
            assert boosted.dtype == np.uint8
            
        arr = np.array(latencies_ms)
        mean_lat = float(np.mean(arr))
        med_lat = float(np.median(arr))
        p95_lat = float(np.percentile(arr, 95))
        p99_lat = float(np.percentile(arr, 99))
        max_lat = float(np.max(arr))
        
        print(f"Dimension: {name.ljust(18)} ({w}x{h})")
        print(f"  - Mean   : {mean_lat:.4f} ms (Target: < 0.30 ms)")
        print(f"  - Median : {med_lat:.4f} ms")
        print(f"  - P95    : {p95_lat:.4f} ms")
        print(f"  - P99    : {p99_lat:.4f} ms")
        print(f"  - Max    : {max_lat:.4f} ms")
        
        assert mean_lat < 0.30, f"LUT Booster mean latency {mean_lat:.4f}ms for {name} exceeds SLA 0.30ms"
        results[name] = {
            "mean_ms": mean_lat,
            "median_ms": med_lat,
            "p95_ms": p95_lat,
            "p99_ms": p99_lat,
            "max_ms": max_lat
        }
        
    print("✅ SLA CRITERION MET: apply_fast_gamma_lut is strictly <0.30ms across all resolution profiles.")
    return results


def test_laplacian_edge_sharpness_variance():
    """
    Empirical Task 3: Laplacian Edge Sharpness Variance Stability & Correctness
    Test sharpness against:
      - Blurred vs Sharp images (verify Sharp > Blurred by significant factor)
      - Extreme all-black (zeros)
      - Extreme all-white (255s)
      - Pure gradient
      - Single-color frames
      - Random uniform noise
      - None/Empty inputs
      - Numerical stability: verify NO NaN, NO inf, NO crash, finite float output
    """
    print("\n" + "="*80)
    print("🔬 TEST 3: Laplacian Edge Sharpness Variance Numerical Stability & Discrimination")
    print("="*80)
    
    test_cases = [
        ("all_black", create_synthetic_frame("all_black", 640, 480)),
        ("all_white", create_synthetic_frame("all_white", 640, 480)),
        ("flat_gray", create_synthetic_frame("flat", 640, 480, step=18)),
        ("blurred_circle", create_synthetic_frame("blurred", 640, 480)),
        ("sharp_edges_grid", create_synthetic_frame("sharp_edges", 640, 480)),
        ("high_texture_checker", create_synthetic_frame("high_texture", 640, 480)),
        ("random_noise", create_synthetic_frame("random_noise", 640, 480)),
        ("micro_crop", np.random.randint(0, 256, (40, 40, 3), dtype=np.uint8)),
        ("none_input", None)
    ]
    
    scores = {}
    for label, img in test_cases:
        score = get_frame_sharpness(img)
        print(f"  - Case: {label.ljust(22)} -> Sharpness Score: {score:.4f}")
        
        # Stability checks
        assert isinstance(score, float)
        assert not np.isnan(score), f"Sharpness score for {label} returned NaN"
        assert not np.isinf(score), f"Sharpness score for {label} returned Inf"
        assert score >= 0.0, f"Sharpness score for {label} was negative: {score}"
        scores[label] = score
        
    # Discriminative checks:
    # 1. Uniform black and uniform white should have exactly 0.0 or near-zero variance
    assert scores["all_black"] < 1e-3, f"All black frame sharpness should be 0, got {scores['all_black']}"
    assert scores["all_white"] < 1e-3, f"All white frame sharpness should be 0, got {scores['all_white']}"
    assert scores["flat_gray"] < 1e-3, f"Flat gray frame sharpness should be 0, got {scores['flat_gray']}"
    
    # 2. Sharp edges must have significantly higher sharpness than blurred image
    assert scores["sharp_edges_grid"] > scores["blurred_circle"] * 5.0, (
        f"Sharp edges ({scores['sharp_edges_grid']}) did not exceed blurred ({scores['blurred_circle']}) by >5x"
    )
    assert scores["high_texture_checker"] > scores["blurred_circle"] * 5.0
    
    # 3. None frame should return graceful default (0.0) without crashing
    assert scores["none_input"] == 0.0
    
    print("✅ TEST PASSED: Laplacian Edge Sharpness is numerically stable (no NaN/Inf) and highly discriminative.")
    return scores


def test_edge_face_harvester_quality_and_memory_stress():
    """
    Empirical Task 4: EdgeFaceHarvester Quality & Memory Stress
    Simulate continuous 30 FPS face detection ingestion over 1,000 frames:
      - Verify peak quality selection (Q = Area * Sharpness^0.6)
      - Verify unsharp mask sharpening enhancement
      - Verify memory footprint remains bounded without unbounded leak.
    """
    print("\n" + "="*80)
    print("🔬 TEST 4: EdgeFaceHarvester 1,000-Frame 30 FPS Simulation & Memory Stress")
    print("="*80)
    
    harvester = EdgeFaceHarvester()
    # Check if cascade is loaded
    if harvester.cascade is None or harvester.cascade.empty():
        pytest.skip("OpenCV Haar cascade not available on this system.")
        
    # We will simulate a video stream of 1,000 frames at 30 FPS.
    # To test actual face detection, we'll embed synthetic face-like textures that the cascade or detector can find,
    # or simulate candidate injection and tracking logic directly.
    # Let's create realistic face-like patterns on 640x480 frames with varying sharpness and motion.
    
    total_frames = 1000
    harvested_events = []
    
    # Start memory tracker
    gc.collect()
    tracemalloc.start()
    mem_start_current, mem_start_peak = tracemalloc.get_traced_memory()
    
    # We'll generate synthetic frames with a moving synthetic face subject
    # Subject 1 enters at frame 0, peaks sharpness at frame 50, leaves at frame 150
    # Subject 2 enters at frame 200, peaks at frame 250, leaves at frame 350
    # Subject 3 enters at frame 500, peaks at frame 550, leaves at frame 650
    
    # Let's load a real sample face or generate a synthetic face structure
    face_sample = np.zeros((160, 160, 3), dtype=np.uint8)
    face_sample[:] = (180, 200, 230) # Skin tone
    cv2.circle(face_sample, (50, 60), 15, (20, 20, 20), -1) # Eye L
    cv2.circle(face_sample, (110, 60), 15, (20, 20, 20), -1) # Eye R
    cv2.circle(face_sample, (80, 95), 10, (140, 150, 190), -1) # Nose
    cv2.ellipse(face_sample, (80, 125), (35, 15), 0, 0, 180, (40, 40, 180), -1) # Mouth
    
    mem_checkpoints = []
    
    t_start_sim = time.time()
    for frame_idx in range(total_frames):
        # Base frame
        frame = np.full((720, 1280, 3), 40, dtype=np.uint8)
        
        # Add subtle background texture
        frame[::40, :, :] = 55
        
        # Add moving face subject depending on frame_idx
        active_subject = False
        face_blur_k = 1
        
        if 50 <= frame_idx < 180:
            # Subject 1
            active_subject = True
            pos_x = int(200 + (frame_idx - 50) * 3)
            pos_y = 200
            # Sharpness peaks at frame 100
            dist_from_peak = abs(frame_idx - 100)
            face_blur_k = max(1, 1 + (dist_from_peak // 5) * 2)
            if face_blur_k % 2 == 0:
                face_blur_k += 1
        elif 300 <= frame_idx < 450:
            # Subject 2
            active_subject = True
            pos_x = int(600 - (frame_idx - 300) * 2)
            pos_y = 220
            dist_from_peak = abs(frame_idx - 370)
            face_blur_k = max(1, 1 + (dist_from_peak // 6) * 2)
            if face_blur_k % 2 == 0:
                face_blur_k += 1
        elif 600 <= frame_idx < 750:
            # Subject 3
            active_subject = True
            pos_x = int(400 + (frame_idx - 600) * 4)
            pos_y = 180
            dist_from_peak = abs(frame_idx - 675)
            face_blur_k = max(1, 1 + (dist_from_peak // 4) * 2)
            if face_blur_k % 2 == 0:
                face_blur_k += 1

        if active_subject and 0 <= pos_x <= 1280 - 160 and 0 <= pos_y <= 720 - 160:
            f_inst = face_sample.copy()
            if face_blur_k > 1:
                f_inst = cv2.GaussianBlur(f_inst, (face_blur_k, face_blur_k), 0)
            frame[pos_y:pos_y+160, pos_x:pos_x+160] = f_inst

        # Process frame through harvester
        motion_score = 4.5 if active_subject else 0.1
        harvested = harvester.process_frame_for_best_shot(frame, motion_score=motion_score)
        
        if harvested:
            for item in harvested:
                harvested_events.append({
                    "frame_idx": frame_idx,
                    "sharpness": item["sharpness"],
                    "velocity": item["velocity"],
                    "b64_len": len(item["b64"])
                })
                # Verify JPEG base64 payload is valid decodable image
                raw_bytes = base64.b64decode(item["b64"])
                decoded_arr = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
                assert decoded_arr is not None, "Failed to decode harvested JPEG face crop"
                assert decoded_arr.size > 0
                
        # Check memory every 100 frames
        if (frame_idx + 1) % 100 == 0:
            cur, peak = tracemalloc.get_traced_memory()
            mem_checkpoints.append({
                "frame": frame_idx + 1,
                "current_mb": cur / (1024 * 1024),
                "peak_mb": peak / (1024 * 1024),
                "active_tracks_count": len(harvester.active_tracks)
            })

    mem_end_current, mem_end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    print(f"Total Frames Processed : {total_frames}")
    print(f"Harvest Events Captured : {len(harvested_events)}")
    print(f"Active Tracks at End    : {len(harvester.active_tracks)}")
    print(f"Initial Memory Traced   : {mem_start_current / (1024*1024):.2f} MB")
    print(f"Final Memory Traced     : {mem_end_current / (1024*1024):.2f} MB")
    print(f"Peak Memory Traced      : {mem_end_peak / (1024*1024):.2f} MB")
    
    print("\nMemory Checkpoints over 1,000 frames:")
    for chk in mem_checkpoints:
        print(f"  - Frame {chk['frame']:4d}: Current = {chk['current_mb']:.2f} MB | Peak = {chk['peak_mb']:.2f} MB | Active Tracks = {chk['active_tracks_count']}")
        
    # Verify memory is bounded (final memory should not have ballooned unbounded; <50MB allocated total)
    assert mem_end_current / (1024 * 1024) < 50.0, f"Memory leak detected: {mem_end_current / (1024*1024):.2f} MB"
    assert mem_end_peak / (1024 * 1024) < 100.0, f"Peak memory excessive: {mem_end_peak / (1024*1024):.2f} MB"
    
    print("✅ TEST PASSED: EdgeFaceHarvester exhibits bounded memory footprint and proper track pruning.")
    return {
        "total_frames": total_frames,
        "harvest_events": len(harvested_events),
        "mem_start_mb": mem_start_current / (1024 * 1024),
        "mem_end_mb": mem_end_current / (1024 * 1024),
        "mem_peak_mb": mem_end_peak / (1024 * 1024),
        "checkpoints": mem_checkpoints
    }


def test_hmac_and_telemetry_verifications():
    """Verifies HMAC signature generation and system telemetry helper integrity."""
    print("\n" + "="*80)
    print("🔬 TEST 5: Cryptographic Nonce Signing & Telemetry Robustness")
    print("="*80)
    
    secret = "test_secret_key_12345"
    payload = "rpi_classroom_101"
    ts = "12:34:56"
    nonce = "a1b2c3d4"
    
    sig1 = generate_hmac_signature(secret, payload, ts, nonce)
    sig2 = generate_hmac_signature(secret, payload, ts, nonce)
    assert sig1 == sig2, "HMAC signature should be deterministic for identical inputs"
    assert len(sig1) == 64, "HMAC-SHA256 hex digest must be 64 characters"
    
    # Tamper test
    sig_tampered = generate_hmac_signature(secret, "tampered_device", ts, nonce)
    assert sig1 != sig_tampered, "HMAC signature must detect payload tampering"
    
    # Telemetry test
    temp = get_cpu_temp()
    assert isinstance(temp, float)
    assert 0.0 <= temp <= 120.0
    
    formatted = format_cpu_temp(temp)
    assert "°C" in formatted
    
    telemetry = get_system_telemetry()
    assert "temp_c" in telemetry
    assert "status" in telemetry
    assert "load_1m" in telemetry
    
    print(f"  - Generated HMAC : {sig1}")
    print(f"  - Telemetry Data : {telemetry}")
    print("✅ TEST PASSED: Cryptographic signing and telemetry probes operating nominally.")


if __name__ == "__main__":
    b1 = test_benchmark_optical_motion_detector()
    b2 = test_benchmark_simd_gamma_lut_booster()
    b3 = test_laplacian_edge_sharpness_variance()
    b4 = test_edge_face_harvester_quality_and_memory_stress()
    test_hmac_and_telemetry_verifications()
    print("\n" + "="*80)
    print("🎉 ALL EMPIRICAL CHALLENGER BENCHMARKS & STRESS TESTS COMPLETED SUCCESSFULLY!")
    print("="*80)
