import cv2
import math
import numpy as np
import mediapipe as mp

# --- BASIC FACE DETECTOR (crowd / distance) ---
mp_face_detection = mp.solutions.face_detection
detector = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.4)

# --- FACE MESH: Blink EAR + Z-Depth Analysis ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh_analyzer = mp_face_mesh.FaceMesh(
    static_image_mode=True,
    max_num_faces=1,
    refine_landmarks=False,
    min_detection_confidence=0.5
)

# Eye Aspect Ratio landmark indices (MediaPipe 468-point mesh)
_R_EYE = [33, 160, 158, 133, 153, 144]   # Right eye: p1..p6
_L_EYE = [362, 385, 387, 263, 373, 380]  # Left eye:  p1..p6

# Depth key-points: nose-tip, chin, forehead, left-cheek, right-cheek
_DEPTH_LM = [4, 152, 10, 234, 454]

def _calc_ear(lms, idx_list, iw, ih):
    """Eye Aspect Ratio from a 6-point eye landmark set."""
    pts = [(lms[i].x * iw, lms[i].y * ih) for i in idx_list]
    p1, p2, p3, p4, p5, p6 = pts
    A = math.sqrt((p2[0]-p6[0])**2 + (p2[1]-p6[1])**2)
    B = math.sqrt((p3[0]-p5[0])**2 + (p3[1]-p5[1])**2)
    C = math.sqrt((p1[0]-p4[0])**2 + (p1[1]-p4[1])**2)
    return (A + B) / (2.0 * C + 1e-6)

def detect_faces_crowd(image_bytes):
    """Detects ALL faces and returns individual crops for AWS processing."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return []

        h, w, _ = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = detector.process(img_rgb)

        face_data = []
        if results.detections:
            for detection in results.detections:
                bbox = detection.location_data.relative_bounding_box

                # Pixel coordinates with 15% padding
                pad = 0.15
                x1 = int((bbox.xmin - bbox.width * pad) * w)
                y1 = int((bbox.ymin - bbox.height * pad) * h)
                x2 = int((bbox.xmin + bbox.width * (1 + pad)) * w)
                y2 = int((bbox.ymin + bbox.height * (1 + pad)) * h)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                face_crop = img[y1:y2, x1:x2]
                if face_crop.size == 0: continue

                _, buffer = cv2.imencode('.jpg', face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                crop_bytes = buffer.tobytes()

                # Basic 6-point landmarks (for parallax/drift tracker)
                landmarks = []
                try:
                    for kp in detection.location_data.relative_keypoints:
                        landmarks.append({"x": kp.x, "y": kp.y})
                except Exception:
                    pass

                # Environmental Analysis (Brightness & Blur) & FFT Anti-Spoofing
                try:
                    gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    brightness = float(np.mean(gray_crop))
                    blur = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
                    f_transform = np.fft.fft2(gray_crop)
                    f_shift = np.fft.fftshift(f_transform)
                    magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1e-8)
                    h_crop, w_crop = gray_crop.shape
                    cy, cx = h_crop // 2, w_crop // 2
                    magnitude_spectrum[max(0, cy-10):cy+10, max(0, cx-10):cx+10] = 0
                    fft_max_hf = float(np.max(magnitude_spectrum))
                except:
                    brightness, blur, fft_max_hf = 100.0, 100.0, 0.0

                # --- GATE 2 & 3: FaceMesh Blink EAR + Z-Depth Variance ---
                ear_val = None
                z_var = None
                try:
                    crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                    mesh_result = face_mesh_analyzer.process(crop_rgb)
                    if mesh_result.multi_face_landmarks:
                        lms = mesh_result.multi_face_landmarks[0].landmark
                        ch, cw = face_crop.shape[:2]
                        r_ear = _calc_ear(lms, _R_EYE, cw, ch)
                        l_ear = _calc_ear(lms, _L_EYE, cw, ch)
                        ear_val = (r_ear + l_ear) / 2.0
                        zs = [lms[i].z for i in _DEPTH_LM]
                        z_var = float(np.var(zs))
                        print(f"[MESH] EAR={ear_val:.3f} Z_VAR={z_var:.6f}")
                except Exception as e:
                    print(f"[FaceMesh] {e}")

                face_data.append({
                    "box": {"x": bbox.xmin, "y": bbox.ymin, "w": bbox.width, "h": bbox.height},
                    "landmarks": landmarks,
                    "bytes": crop_bytes,
                    "brightness": brightness,
                    "blur": blur,
                    "fft_max_hf": fft_max_hf,
                    "ear": ear_val,       # Eye Aspect Ratio (blink gate)
                    "z_variance": z_var   # Depth variance (flat-surface gate)
                })

        return face_data
    except Exception as e:
        print(f"Detector Error: {e}")
        return []

# Unified naming for stability
detect_faces_ultra = detect_faces_crowd
detect_faces_local = detect_faces_crowd
