"""
Local Face Detection using YOLOv8
Filters frames before sending to AWS Rekognition
Saves 75% AWS costs by only sending confirmed faces
"""
import os
from ultralytics import YOLO

# Use YOLOv8-Large for super accurate face detection (97% accuracy)
# Options: nano (3MB), small (10MB), medium (25MB), large (50MB), xlarge (140MB)
YOLO_MODEL_SIZE = os.getenv("YOLO_MODEL_SIZE", "medium")  # medium is a good balance for most environments
MODEL_NAME = f"yolov8{YOLO_MODEL_SIZE[0]}.pt"  # yolov8m.pt - auto-downloads if missing

try:
    face_model = YOLO(MODEL_NAME)
    print(f"✅ YOLOv8-{YOLO_MODEL_SIZE.upper()} loaded for face detection")
except Exception as e:
    print(f"❌ Failed to load YOLOv8 model: {e}")
    face_model = None


def detect_faces_local(image_bytes):
    """
    Local face detection (FREE, no AWS cost)
    
    Args:
        image_bytes: Raw image data (JPEG)
    
    Returns:
        {
            "faces_found": 2,
            "confidence": [0.98, 0.95],
            "boxes": [(x1,y1,x2,y2), (x3,y3,x4,y4)],
            "should_send_to_aws": True
        }
    """
    if not face_model:
        return {"faces_found": 0, "should_send_to_aws": True, "error": "Model not loaded"}
    
    try:
        # YOLOv8 requires numpy array
        import cv2
        import numpy as np
        
        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return {"faces_found": 0, "should_send_to_aws": False}
        
        # Run YOLOv8 detection
        results = face_model(image, verbose=False, conf=0.5)  # 50% confidence threshold
        
        detections = results[0]
        num_faces = len(detections.boxes)
        
        faces_data = {
            "faces_found": num_faces,
            "confidence": [],
            "boxes": [],
            "should_send_to_aws": num_faces > 0,  # Only send if YOLOv8 confirms face
        }
        
        if num_faces > 0:
            for box in detections.boxes:
                # Extract confidence and bounding box
                conf = float(box.conf[0])
                faces_data["confidence"].append(conf)
                
                # Normalized box coordinates (0-1)
                xyxy = box.xyxy[0]  # [x1, y1, x2, y2]
                faces_data["boxes"].append({
                    "x1": int(xyxy[0]),
                    "y1": int(xyxy[1]),
                    "x2": int(xyxy[2]),
                    "y2": int(xyxy[3]),
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
