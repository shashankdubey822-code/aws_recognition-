import cv2
import numpy as np
import mediapipe as mp

# --- INITIALIZE MULTI-STAGE DETECTORS ---
mp_face_mesh = mp.solutions.face_mesh
mp_face_detection = mp.solutions.face_detection

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=True, max_num_faces=1, refine_landmarks=True,
    min_detection_confidence=0.4, min_tracking_confidence=0.4
)

fallback_detector = mp_face_detection.FaceDetection(
    model_selection=1, min_detection_confidence=0.3
)

def get_diagnostics(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    avg_brightness = np.mean(gray)
    blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()
    diag = {"status": "ok", "msg": ""}
    if avg_brightness < 45:
        diag = {"status": "low_light", "msg": "⚠️ Environment too dark."}
    elif blur_value < 10:
        diag = {"status": "blurry", "msg": "⚠️ Image blurry. Hold still."}
    return diag

def detect_faces_ultra(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return {"faces_found": 0, "diag": {"msg": "No data"}}
        
        h, w, _ = img.shape
        diag = get_diagnostics(img)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 1. Try Face Mesh (High Precision)
        results = face_mesh.process(img_rgb)
        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0]
            # Calculate Bounding Box from Landmarks
            x_coords = [p.x for p in lm.landmark]
            y_coords = [p.y for p in lm.landmark]
            box = {
                "x": min(x_coords), "y": min(y_coords),
                "w": max(x_coords) - min(x_coords), "h": max(y_coords) - min(y_coords)
            }
            # Relative Yaw (Nose vs Face Center)
            yaw = (lm.landmark[1].x - 0.5) * 100
            return {"faces_found": 1, "precision": "high", "box": box, "pose": {"yaw": yaw}, "diag": diag}
            
        # 2. Try BlazeFace (Robust Fallback)
        fb_results = fallback_detector.process(img_rgb)
        if fb_results.detections:
            d = fb_results.detections[0].location_data.relative_bounding_box
            box = {"x": d.xmin, "y": d.ymin, "w": d.width, "h": d.height}
            return {"faces_found": 1, "precision": "low", "box": box, "diag": diag}

        return {"faces_found": 0, "diag": diag if diag["msg"] else {"msg": "🔍 Searching..."}}
    except Exception as e:
        return {"faces_found": 0, "diag": {"msg": f"Error: {str(e)[:20]}"}}

detect_faces_local = detect_faces_ultra
