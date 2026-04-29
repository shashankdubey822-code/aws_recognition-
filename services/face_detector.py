import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace
import os

# --- ENTERPRISE NEURAL CONFIG ---
# Disable TensorFlow logging to keep terminal clean
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1)

print("🧠 Pre-loading Facenet512 Engine...")
# Force model load into RAM immediately
DeepFace.build_model("Facenet512")

def detect_faces_ultra(image_bytes):
    """Detects face and returns the cropped face for the embedding engine"""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return {"faces_found": 0}
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(img_rgb)
        
        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0]
            h, w, _ = img.shape
            x_coords = [p.x * w for p in lm.landmark]
            y_coords = [p.y * h for p in lm.landmark]
            
            # Create a tight crop with 20% padding for better DeepFace accuracy
            x1, y1 = int(min(x_coords)), int(min(y_coords))
            x2, y2 = int(max(x_coords)), int(max(y_coords))
            
            # Ensure crop is within bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            face_crop = img[y1:y2, x1:x2]
            
            # Return normalized box for UI
            box = {"x": min(x_coords)/w, "y": min(y_coords)/h, "w": (x2-x1)/w, "h": (y2-y1)/h}
            
            return {
                "faces_found": 1,
                "box": box,
                "face_img": face_crop
            }
        return {"faces_found": 0}
    except:
        return {"faces_found": 0}

def get_embedding_batch(face_images):
    """Processes a batch of images into a single averaged 512-dim vector"""
    embeddings = []
    for face_img in face_images:
        try:
            # enforce_detection=False because we already cropped the face
            obj = DeepFace.represent(face_img, model_name="Facenet512", enforce_detection=False, align=False)
            if obj:
                embeddings.append(obj[0]["embedding"])
        except:
            continue
    
    if not embeddings: return None
    return np.mean(embeddings, axis=0)

detect_faces_local = detect_faces_ultra
