import sys
import os
import time
import urllib.request

# 1. Auto-install dependencies if they are missing
try:
    import cv2
    from ultralytics import YOLO
except ImportError:
    print("Installing required packages (ultralytics, opencv-python)...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "ultralytics", "opencv-python"])
    import cv2
    from ultralytics import YOLO

def main():
    # 2. Load the model
    model_url = "https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt"
    model_path = "yolov8n-face.pt"
    
    if not os.path.exists(model_path):
        print(f"Downloading YOLOv8-Face model weights ({model_path})...")
        try:
            req = urllib.request.Request(
                model_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req) as response, open(model_path, 'wb') as out_file:
                out_file.write(response.read())
            print("Download complete!")
        except Exception as e:
            print(f"Failed to download model weights: {e}")
            print("Trying fallback to official YOLOv8n general detection weights...")
            # Fallback to standard yolov8n.pt if face weights cannot be fetched
            model_path = "yolov8n.pt"

    print(f"Loading model '{model_path}' into memory...")
    model = YOLO(model_path)
    
    # 3. Create a test image with synthetic faces
    test_image_path = "yolo_test_input.jpg"
    if not os.path.exists(test_image_path):
        print("Creating a dummy test image for benchmarking...")
        import numpy as np
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw some white circles to simulate "face" spots
        cv2.circle(img, (150, 240), 50, (255, 255, 255), -1)
        cv2.circle(img, (320, 240), 60, (255, 255, 255), -1)
        cv2.circle(img, (490, 240), 45, (255, 255, 255), -1)
        cv2.putText(img, "Simulation: 3 Face Spots", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imwrite(test_image_path, img)

    # 4. Perform Inference and Benchmark Speed
    print(f"Running face detection on '{test_image_path}'...")
    start_time = time.time()
    
    results = model(test_image_path, conf=0.25)
    
    inference_time = (time.time() - start_time) * 1000
    print(f"\nBenchmark Results:")
    print(f"Total processing time: {inference_time:.2f} ms")
    
    # 5. Process results
    result = results[0]
    boxes = result.boxes
    print(f"Faces/Objects detected: {len(boxes)}")
    
    # Load image to draw boxes on
    img = cv2.imread(test_image_path)
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        print(f"   - Match {i+1}: Bounding Box [{x1}, {y1}, {x2}, {y2}] | Confidence: {conf*100:.1f}%")
        
        # Draw box and label
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, f"Match {i+1} ({conf*100:.0f}%)", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Save output
    output_path = "yolo_test_result.jpg"
    cv2.imwrite(output_path, img)
    print(f"\nMarked output saved to: {output_path}")
    print("Done!")

if __name__ == "__main__":
    main()
