import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace

# --- MULTI-AGENT DETECTOR SETUP ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True)

# Pre-load model to RAM (512-dimensional output)
print("🧠 Loading FaceNet512 Neural Engine...")
DeepFace.build_model("Facenet512")

def extract_embedding_512(img):
    """Generates a high-precision 512-dimensional vector"""
    try:
        # We use DeepFace to represent the face as a 512-dim list
        # detector_backend="mediapipe" as per gemini.md mandate
        objs = DeepFace.represent(
            img, 
            model_name="Facenet512", 
            detector_backend="mediapipe",
            enforce_detection=True,
            align=True
        )
        if objs:
            return np.array(objs[0]["embedding"])
        return None
    except Exception as e:
        return None

def detect_faces_ultra(image_bytes):
    """Diagnostic + Bounding Box + Metadata"""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return {"faces_found": 0}
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(img_rgb)
        
        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0]
            x_coords = [p.x for p in lm.landmark]
            y_coords = [p.y for p in lm.landmark]
            box = {"x": min(x_coords), "y": min(y_coords), "w": max(x_coords)-min(x_coords), "h": max(y_coords)-min(y_coords)}
            yaw = (lm.landmark[1].x - 0.5) * 100
            
            return {
                "faces_found": 1,
                "box": box,
                "pose": {"yaw": yaw},
                "raw_img": img # Return for further embedding processing
            }
        return {"faces_found": 0}
    except:
        return {"faces_found": 0}

detect_faces_local = detect_faces_ultra
