import cv2
import numpy as np
import mediapipe as mp
from scipy.spatial import distance as dist

# --- HIGH-ACCURACY ENGINE CONFIG ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

def get_head_pose(landmarks, img_w, img_h):
    """
    Calculates Head Pose (Yaw, Pitch, Roll) using 3D points
    """
    # Specific landmarks for pose estimation
    # 1: Nose tip, 152: Chin, 33: Left eye corner, 263: Right eye corner, 61: Left mouth, 291: Right mouth
    face_3d = []
    face_2d = []
    
    for idx, lm in enumerate(landmarks.landmark):
        if idx in [1, 152, 33, 263, 61, 291]:
            x, y = int(lm.x * img_w), int(lm.y * img_h)
            face_2d.append([x, y])
            face_3d.append([x, y, lm.z]) # lm.z is already scaled roughly

    face_2d = np.array(face_2d, dtype=np.float64)
    face_3d = np.array(face_3d, dtype=np.float64)

    # Camera Matrix
    focal_length = 1 * img_w
    cam_matrix = np.array([ [focal_length, 0, img_h / 2],
                            [0, focal_length, img_w / 2],
                            [0, 0, 1]], dtype=np.float64)
    dist_matrix = np.zeros((4, 1), dtype=np.float64)

    # Solve PnP
    success, rot_vec, trans_vec = cv2.solvePnP(face_3d, face_2d, cam_matrix, dist_matrix)
    rmat, _ = cv2.Rodrigues(rot_vec)
    angles, _, _, _, _, _ = cv2.decomposeProjectionMatrix(np.hstack((rmat, trans_vec)))

    # Convert to Degrees
    pitch, yaw, roll = angles[0] * 360, angles[1] * 360, angles[2] * 360
    return yaw, pitch, roll

def get_eye_aspect_ratio(landmarks, eye_indices):
    """Calculates Eye Aspect Ratio (EAR) for blink detection"""
    points = []
    for idx in eye_indices:
        lm = landmarks.landmark[idx]
        points.append([lm.x, lm.y])
    
    points = np.array(points)
    # Vertical distances
    v1 = dist.euclidean(points[1], points[5])
    v2 = dist.euclidean(points[2], points[4])
    # Horizontal distance
    h = dist.euclidean(points[0], points[3])
    return (v1 + v2) / (2.0 * h)

def detect_faces_ultra(image_bytes):
    """
    Advanced real-time pose and identity validator
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return None
        
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, _ = img.shape
        results = face_mesh.process(img_rgb)
        
        if not results.multi_face_landmarks:
            return {"faces_found": 0}

        landmarks = results.multi_face_landmarks[0]
        yaw, pitch, roll = get_head_pose(landmarks, w, h)
        
        # Blink Detection (EAR)
        left_ear = get_eye_aspect_ratio(landmarks, [362, 385, 387, 263, 373, 380])
        right_ear = get_eye_aspect_ratio(landmarks, [33, 160, 158, 133, 153, 144])
        ear = (left_ear + right_ear) / 2.0

        return {
            "faces_found": 1,
            "pose": {"yaw": yaw, "pitch": pitch, "roll": roll},
            "liveness": {"ear": ear, "is_blinking": ear < 0.2},
            "should_send_to_aws": True # Still send for full recognition
        }
    except Exception as e:
        print(f"Ultra Detector Error: {e}")
        return {"faces_found": 0, "error": str(e)}
