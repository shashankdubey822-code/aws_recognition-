import cv2
import numpy as np
import mediapipe as mp

# --- INITIALIZE MULTI-STAGE DETECTORS ---
mp_face_mesh = mp.solutions.face_mesh
mp_face_detection = mp.solutions.face_detection # Secondary robust detector

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=True, max_num_faces=1, refine_landmarks=True,
    min_detection_confidence=0.4, min_tracking_confidence=0.4
)

# BlazeFace: Much more robust to low light than Face Mesh
fallback_detector = mp_face_detection.FaceDetection(
    model_selection=1, min_detection_confidence=0.3
)

def get_diagnostics(img):
    """Analyzes environment: Brightness, Blur, and Contrast"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Brightness Check
    avg_brightness = np.mean(gray)
    
    # 2. Blur Check (Laplacian Variance)
    blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 3. Contrast Check
    contrast = gray.std()
    
    diag = {"status": "ok", "msg": ""}
    
    if avg_brightness < 45:
        diag = {"status": "low_light", "msg": "⚠️ Environment too dark. Increase lighting."}
    elif blur_value < 10:
        diag = {"status": "blurry", "msg": "⚠️ Image blurry. Hold still."}
    elif contrast < 20:
        diag = {"status": "low_contrast", "msg": "⚠️ Low contrast. Face not distinct from background."}
        
    return diag, avg_brightness

def detect_faces_ultra(image_bytes):
    """
    Diagnostic-aware detection engine
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return {"faces_found": 0, "diag": "No image data"}
        
        h, w, _ = img.shape
        diag, brightness = get_diagnostics(img)
        
        # Try High-Precision Mesh first
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(img_rgb)
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0]
            # Simple yaw calculation from landmarks
            # Nose (1) vs Left (33) and Right (263)
            nos = landmarks.landmark[1].x
            yaw = (nos - 0.5) * 100 # Rough approximation for pose rules
            
            return {
                "faces_found": 1,
                "precision": "high",
                "pose": {"yaw": yaw},
                "diag": diag
            }
            
        # Fallback to Robust BlazeFace
        fallback_results = fallback_detector.process(img_rgb)
        if fallback_results.detections:
            return {
                "faces_found": 1,
                "precision": "low", # Can't do 3D pose, but knows you are there
                "diag": {"status": "low_precision", "msg": "⚠️ Pose unknown. Look directly at camera."}
            }

        # If both fail, return the diagnostic reason
        return {
            "faces_found": 0,
            "diag": diag if diag["status"] != "ok" else {"status": "no_face", "msg": "🔍 Searching for face..."}
        }
    except Exception as e:
        return {"faces_found": 0, "diag": {"status": "error", "msg": f"Module Error: {str(e)[:20]}"}}

detect_faces_local = detect_faces_ultra
