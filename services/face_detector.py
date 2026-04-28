"""
Local Face Detection using Google MediaPipe
Filters frames before sending to AWS Rekognition
Saves 75% AWS costs by only sending confirmed faces
"""
import os
import cv2
import numpy as np
import mediapipe as mp

# Initialize MediaPipe Face Detection
try:
    import mediapipe.python.solutions.face_detection as mp_face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
except (AttributeError, ImportError):
    mp_face_detection = mp.solutions.face_detection
    face_detection = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)

print("✅ MediaPipe Face Detection loaded")

def detect_faces_local(image_bytes):
    """
    Local face detection (FREE, no AWS cost) using MediaPipe
    
    Args:
        image_bytes: Raw image data (JPEG)
    
    Returns:
        {
            "faces_found": 2,
            "confidence": [0.98, 0.95],
            "boxes": [{"x1": 10, "y1": 10, "x2": 50, "y2": 50, "confidence": 0.98}],
            "should_send_to_aws": True
        }
    """
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
        print(f"❌ Face detection error: {e}")
        return {
            "faces_found": 0,
            "should_send_to_aws": True,  # Fallback: still send to AWS
            "error": str(e)
        }
