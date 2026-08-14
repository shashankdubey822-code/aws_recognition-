import cv2
import numpy as np
import mediapipe as mp

# --- ROBUST MULTI-FACE DETECTOR ---
mp_face_detection = mp.solutions.face_detection

def detect_faces_crowd(image_bytes):
    """Detects ALL faces and returns individual crops for processing."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return []

        h, w, _ = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Instantiate detector per call to prevent timestamp mismatch in C++ graph across async threads
        with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.4) as detector:
            results = detector.process(img_rgb)

            face_data = []
            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box

                # Pixel coordinates with 15% padding
                pad = 0.15
                x1 = int((bbox.xmin - bbox.width * pad) * w)
                y1 = int((bbox.ymin - bbox.height * pad) * h)
                x2 = int((bbox.xmin + bbox.width * (1 + pad)) * w)
                y2 = int((bbox.ymin + bbox.height * (1 + pad)) * h)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                face_crop = img[y1:y2, x1:x2]
                if face_crop.size == 0: continue

                _, buffer = cv2.imencode('.jpg', face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                crop_bytes = buffer.tobytes()

                # Extract 6-point facial landmarks for challenge-response positioning
                landmarks = []
                try:
                    for kp in detection.location_data.relative_keypoints:
                        landmarks.append({"x": kp.x, "y": kp.y})
                except Exception:
                    pass

                # Environmental Analysis (Brightness & Blur) & FFT Anti-Spoofing
                try:
                    gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    brightness = float(np.mean(gray_crop))
                    blur = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())

                    # FFT: detect high-frequency repeating grids (digital screens / moiré)
                    f_transform = np.fft.fft2(gray_crop)
                    f_shift = np.fft.fftshift(f_transform)
                    magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1e-8)
                    h_crop, w_crop = gray_crop.shape
                    cy, cx = h_crop // 2, w_crop // 2
                    magnitude_spectrum[max(0, cy-10):cy+10, max(0, cx-10):cx+10] = 0
                    fft_max_hf = float(np.max(magnitude_spectrum))
                except:
                    brightness, blur, fft_max_hf = 100.0, 100.0, 0.0

                face_data.append({
                    "box": {"x": bbox.xmin, "y": bbox.ymin, "w": bbox.width, "h": bbox.height},
                    "landmarks": landmarks,
                    "bytes": crop_bytes,
                    "brightness": brightness,
                    "blur": blur,
                    "fft_max_hf": fft_max_hf
                })

        return face_data
    except Exception as e:
        print(f"Detector Error: {e}")
        return []

# Unified naming for stability
detect_faces_ultra = detect_faces_crowd
detect_faces_local = detect_faces_crowd
