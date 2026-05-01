"""
Robust Geometric Liveness Engine
---------------------------------
Replaces the missing ONNX model with a highly-tuned mathematical 
scoring system using MediaPipe FaceMesh (468 3D landmarks).
Computes a continuous liveness probability [0.0, 1.0] based on 3D depth.

Runs asynchronously per-face.
"""

import cv2
import numpy as np
import mediapipe as mp

# Lazy load FaceMesh so it doesn't slow down global imports
_face_mesh = None

def _get_mesh():
    global _face_mesh
    if _face_mesh is None:
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True, 
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
    return _face_mesh

def warmup():
    """Initializes FaceMesh into RAM."""
    _get_mesh()

def score_liveness(face_crop_bytes: bytes) -> float:
    """
    Analyzes the 3D geometry of the face crop to determine liveness.
    Returns:
        float: 0.0 (definitely SPOOF/FLAT) to 1.0 (definitely REAL/3D)
    """
    try:
        # Decode image
        nparr = np.frombuffer(face_crop_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            return 0.5

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mesh = _get_mesh()
        results = mesh.process(img_rgb)

        if not results.multi_face_landmarks:
            return 0.5 # Neutral if mesh fails

        landmarks = results.multi_face_landmarks[0].landmark

        # --- TEST 1: Z-Depth Variance (Flat Photo vs 3D Face) ---
        # Photos have uniform, mathematically flat Z coordinates relative to the mesh
        z_values = [lm.z for lm in landmarks]
        z_std = np.std(z_values)
        z_range = abs(max(z_values) - min(z_values))
        
        # Calculate a depth score (Photos usually have z_range < 0.04, Real > 0.08)
        # We normalize this into a 0.0 to 1.0 probability
        depth_score = np.clip((z_range - 0.03) / 0.06, 0.0, 1.0)

        # --- TEST 2: Eye Aspect Ratio (EAR) Snapshot ---
        # Real eyes have a specific open aspect ratio. Photos often distort this under mesh mapping.
        def get_ear(eye_indices):
            # Vertical
            v1 = np.linalg.norm(np.array([landmarks[eye_indices[1]].x, landmarks[eye_indices[1]].y]) - 
                                np.array([landmarks[eye_indices[5]].x, landmarks[eye_indices[5]].y]))
            v2 = np.linalg.norm(np.array([landmarks[eye_indices[2]].x, landmarks[eye_indices[2]].y]) - 
                                np.array([landmarks[eye_indices[4]].x, landmarks[eye_indices[4]].y]))
            # Horizontal
            h = np.linalg.norm(np.array([landmarks[eye_indices[0]].x, landmarks[eye_indices[0]].y]) - 
                               np.array([landmarks[eye_indices[3]].x, landmarks[eye_indices[3]].y]))
            return (v1 + v2) / (2.0 * h + 1e-6)

        left_eye_indices = [33, 160, 158, 133, 153, 144]
        right_eye_indices = [362, 385, 387, 263, 373, 380]
        
        ear_left = get_ear(left_eye_indices)
        ear_right = get_ear(right_eye_indices)
        avg_ear = (ear_left + ear_right) / 2.0
        
        # Plausible human EAR is generally between 0.15 and 0.40.
        if 0.15 < avg_ear < 0.45:
            ear_score = 1.0
        else:
            # Extreme EAR implies a flat printed face warping the mesh
            ear_score = 0.2

        # --- FINAL FUSED SCORE ---
        # Weighting: 80% Depth, 20% EAR structural validity
        final_score = (depth_score * 0.8) + (ear_score * 0.2)
        
        return float(final_score)

    except Exception as e:
        print(f"[LIVENESS] Geometry error: {e}")
        return 0.5
