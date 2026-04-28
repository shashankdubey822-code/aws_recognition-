"""
Local Face Detection using Google MediaPipe
Filters frames before sending to AWS Rekognition
Saves 75% AWS costs by only sending confirmed faces
"""
import os
import cv2
import numpy as np

# Initialize MediaPipe Face Detection with heavy error handling
face_detection = None
try:
    import mediapipe as mp
    # Try multiple import styles for different environments
    if hasattr(mp, 'solutions'):
        mp_face_detection = mp.solutions.face_detection
    else:
        import mediapipe.python.solutions.face_detection as mp_face_detection
        
    face_detection = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
    print("✅ MediaPipe Face Detection loaded successfully")
except Exception as e:
    print(f"⚠️ MediaPipe load failed: {e}. Falling back to AWS-only detection.")
    face_detection = None

def detect_faces_local(image_bytes):
    """
    Local face detection (FREE, no AWS cost) using MediaPipe
    If MediaPipe is not available, defaults to True to ensure system works.
    """
    if face_detection is None:
        # Fallback: Always send to AWS if local detection is broken
        return {
            "faces_found": 1, 
            "should_send_to_aws": True, 
            "info": "mediapipe_unavailable_fallback"
        }

    try:
        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"faces_found": 0, "should_send_to_aws": False}
            
        # Convert the BGR image to RGB as required by MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width, _ = image.shape
        
        # Process the image and find faces
        results = face_detection.process(image_rgb)
        
        faces_data = {
            "faces_found": 0,
            "confidence": [],
            "boxes": [],
            "should_send_to_aws": False
        }
        
        if results.detections:
            num_faces = len(results.detections)
            faces_data["faces_found"] = num_faces
            faces_data["should_send_to_aws"] = num_faces > 0
            
            for detection in results.detections:
                conf = float(detection.score[0])
                faces_data["confidence"].append(conf)
                
                # Bounding box is relative to image size [0, 1]
                bbox = detection.location_data.relative_bounding_box
                x1 = int(bbox.xmin * width)
                y1 = int(bbox.ymin * height)
                w = int(bbox.width * width)
                h = int(bbox.height * height)
                x2 = x1 + w
                y2 = y1 + h
                
                faces_data["boxes"].append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": conf
                })
                
        return faces_data
        
    except Exception as e:
        print(f"❌ Face detection runtime error: {e}")
        return {
            "faces_found": 1,
            "should_send_to_aws": True,
            "error": str(e)
        }
