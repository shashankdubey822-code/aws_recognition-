import cv2
import numpy as np
import mediapipe as mp
from scipy.spatial import distance as dist

# --- ROBUST ENGINE CONFIG ---
mp_face_mesh = mp.solutions.face_mesh
# static_image_mode=True is MUCH more stable for WebSocket/Network streams
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=True, 
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5, # Lowered from 0.7 for better indoor detection
    min_tracking_confidence=0.5
)

def get_head_pose(landmarks, img_w, img_h):
    """Calculates Head Pose (Yaw, Pitch, Roll)"""
    face_3d = []
    face_2d = []
    for idx, lm in enumerate(landmarks.landmark):
        if idx in [1, 152, 33, 263, 61, 291]:
            x, y = int(lm.x * img_w), int(lm.y * img_h)
            face_2d.append([x, y])
            face_3d.append([x, y, lm.z])
    face_2d = np.array(face_2d, dtype=np.float64)
    face_3d = np.array(face_3d, dtype=np.float64)
    focal_length = 1 * img_w
    cam_matrix = np.array([[focal_length, 0, img_h/2], [0, focal_length, img_w/2], [0, 0, 1]], dtype=np.float64)
    dist_matrix = np.zeros((4, 1), dtype=np.float64)
    success, rot_vec, trans_vec = cv2.solvePnP(face_3d, face_2d, cam_matrix, dist_matrix)
    rmat, _ = cv2.Rodrigues(rot_vec)
    angles, _, _, _, _, _ = cv2.decomposeProjectionMatrix(np.hstack((rmat, trans_vec)))
    return angles[1] * 360, angles[0] * 360, angles[2] * 360 # Yaw, Pitch, Roll

def detect_faces_ultra(image_bytes):
    """Robust real-time detector optimized for network jitter"""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return {"faces_found": 0}
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, _ = img.shape
        results = face_mesh.process(img_rgb)
        
        if not results.multi_face_landmarks:
            return {"faces_found": 0}

        landmarks = results.multi_face_landmarks[0]
        yaw, pitch, roll = get_head_pose(landmarks, w, h)
        
        return {
            "faces_found": 1,
            "pose": {"yaw": yaw, "pitch": pitch, "roll": roll},
            "should_send_to_aws": True
        }
    except Exception as e:
        print(f"Detector Error: {e}")
        return {"faces_found": 0}

# Backwards compatibility alias
detect_faces_local = detect_faces_ultra
