import cv2
import numpy as np
import mediapipe as mp

# --- ROBUST MULTI-FACE DETECTOR ---
mp_face_detection = mp.solutions.face_detection
# model_selection=1 is optimized for faces within 5 meters (Better for crowds)
detector = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.4)

def detect_faces_crowd(image_bytes):
    """Detects ALL faces and returns individual crops for AWS processing"""
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
                
                # Calculate pixel coordinates with 15% padding for better AWS accuracy
                pad = 0.15
                x1 = int((bbox.xmin - bbox.width * pad) * w)
                y1 = int((bbox.ymin - bbox.height * pad) * h)
                x2 = int((bbox.xmin + bbox.width * (1 + pad)) * w)
                y2 = int((bbox.ymin + bbox.height * (1 + pad)) * h)
                
                # Constrain to image boundaries
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                
                face_crop = img[y1:y2, x1:x2]
                if face_crop.size == 0: continue
                
                # Convert crop to bytes for AWS
                _, buffer = cv2.imencode('.jpg', face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                crop_bytes = buffer.tobytes()
                
                face_data.append({
                    "box": {"x": bbox.xmin, "y": bbox.ymin, "w": bbox.width, "h": bbox.height},
                    "bytes": crop_bytes,
                    "id": detection.index[0] if hasattr(detection, 'index') else 0
                })
                
        return face_data
    except Exception as e:
        print(f"Crowd Detector Error: {e}")
        return []

# Backwards compatibility
detect_faces_ultra = detect_faces_crowd
detect_faces_local = detect_faces_crowd
