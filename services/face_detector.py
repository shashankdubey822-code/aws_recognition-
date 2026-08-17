import os
import urllib.request
import cv2
import numpy as np
import onnxruntime

class SCRFDFaceDetector:
    """
    InsightFace SCRFD (Sample and Computation Redistribution for Face Detection).
    High-density multi-scale face detector optimized for classroom surveillance & wide-angle cameras.
    """
    def __init__(self, model_path="models/scrfd_2.5g_bnkps.onnx", conf_threshold=0.45, nms_threshold=0.4):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.fmc = 3
        self._feat_stride_fpn = [8, 16, 32]
        self._num_anchors = 2
        self.center_cache = {}
        self.session = None

        self._ensure_model_loaded()

    def _ensure_model_loaded(self):
        if self.session is not None:
            return

        if not os.path.exists(self.model_path):
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            print(f"[SCRFD] Model weights not found locally. Downloading to '{self.model_path}'...")
            urls = [
                "https://huggingface.co/RuteNL/SCRFD-face-detection-ONNX/resolve/main/2.5g_bnkps.onnx",
                "https://github.com/deepinsight/insightface/releases/download/v0.7/scrfd_2.5g_kps.onnx"
            ]
            downloaded = False
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=30) as resp, open(self.model_path, 'wb') as f:
                        f.write(resp.read())
                    if os.path.exists(self.model_path) and os.path.getsize(self.model_path) > 1000000:
                        downloaded = True
                        print(f"[SCRFD] [OK] Download complete ({os.path.getsize(self.model_path)} bytes).")
                        break
                except Exception as e:
                    print(f"[SCRFD] Download attempt failed from {url}: {e}")

            if not downloaded:
                raise RuntimeError(f"Failed to fetch SCRFD model weights from cloud mirrors.")

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 4
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.session = onnxruntime.InferenceSession(
            self.model_path, 
            sess_options=opts, 
            providers=['CPUExecutionProvider']
        )
        self.input_name = self.session.get_inputs()[0].name
        print(f"[SCRFD] [OK] InsightFace SCRFD Engine Initialized (Model: {self.model_path})")

    def detect_faces(self, image_bytes):
        """
        Runs SCRFD multi-scale face detection on raw image bytes.
        Returns clean cropped face payloads with relative coordinates and 5-point landmarks.
        """
        try:
            if not image_bytes:
                return []

            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return []

            img_h, img_w, _ = img.shape
            self._ensure_model_loaded()

            # Preprocessing & Letterboxing for 640x640 input
            input_size = (640, 640)
            im_ratio = float(img_h) / img_w
            model_ratio = float(input_size[1]) / input_size[0]
            
            if im_ratio > model_ratio:
                new_height = input_size[1]
                new_width = int(new_height / im_ratio)
            else:
                new_width = input_size[0]
                new_height = int(new_width * im_ratio)

            det_scale = float(new_height) / img_h
            resized_img = cv2.resize(img, (new_width, new_height))
            
            det_img = np.zeros((input_size[1], input_size[0], 3), dtype=np.uint8)
            det_img[:new_height, :new_width, :] = resized_img

            # Mean (127.5), Scale (1/128), BGR -> RGB
            blob = cv2.dnn.blobFromImage(det_img, 1.0 / 128.0, input_size, (127.5, 127.5, 127.5), swapRB=True)
            net_outs = self.session.run(None, {self.input_name: blob})

            input_height, input_width = blob.shape[2], blob.shape[3]
            fmc = self.fmc

            scores_list = []
            bboxes_list = []
            kpss_list = []

            # Decode outputs across feature strides (8, 16, 32)
            for idx, stride in enumerate(self._feat_stride_fpn):
                score = net_outs[idx]
                bbox = net_outs[idx + fmc]
                kps = net_outs[idx + fmc * 2]

                stride_h = input_height // stride
                stride_w = input_width // stride
                key = (stride_h, stride_w, stride)

                if key in self.center_cache:
                    anchor_centers = self.center_cache[key]
                else:
                    anchor_centers = np.stack(np.mgrid[:stride_h, :stride_w][::-1], axis=-1).astype(np.float32)
                    anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                    if self._num_anchors > 1:
                        anchor_centers = np.stack([anchor_centers] * self._num_anchors, axis=1).reshape((-1, 2))
                    if len(self.center_cache) < 100:
                        self.center_cache[key] = anchor_centers

                pos_inds = np.where(score[0, :, 0] >= self.conf_threshold)[0]
                if len(pos_inds) == 0:
                    continue

                score = score[0, pos_inds, :]
                bbox = bbox[0, pos_inds, :] * stride
                kps = kps[0, pos_inds, :] * stride
                anchors = anchor_centers[pos_inds, :]

                x1 = (anchors[:, 0] - bbox[:, 0]) / det_scale
                y1 = (anchors[:, 1] - bbox[:, 1]) / det_scale
                x2 = (anchors[:, 0] + bbox[:, 2]) / det_scale
                y2 = (anchors[:, 1] + bbox[:, 3]) / det_scale

                boxes = np.stack([x1, y1, x2, y2], axis=-1)
                scores_list.append(score)
                bboxes_list.append(boxes)

                kpss = np.zeros_like(kps)
                for p in range(5):
                    kpss[:, p * 2] = (anchors[:, 0] + kps[:, p * 2]) / det_scale
                    kpss[:, p * 2 + 1] = (anchors[:, 1] + kps[:, p * 2 + 1]) / det_scale
                kpss_list.append(kpss)

            if len(bboxes_list) == 0:
                return []

            bboxes = np.vstack(bboxes_list)
            scores = np.vstack(scores_list)
            kpss = np.vstack(kpss_list).reshape((-1, 5, 2))

            # Non-Maximum Suppression (NMS)
            order = scores.ravel().argsort()[::-1]
            keep = []
            x1 = bboxes[:, 0]
            y1 = bboxes[:, 1]
            x2 = bboxes[:, 2]
            y2 = bboxes[:, 3]
            areas = (x2 - x1 + 1) * (y2 - y1 + 1)

            while order.size > 0:
                i = order[0]
                keep.append(i)
                xx1 = np.maximum(x1[i], x1[order[1:]])
                yy1 = np.maximum(y1[i], y1[order[1:]])
                xx2 = np.minimum(x2[i], x2[order[1:]])
                yy2 = np.minimum(y2[i], y2[order[1:]])

                w_box = np.maximum(0.0, xx2 - xx1 + 1)
                h_box = np.maximum(0.0, yy2 - yy1 + 1)
                inter = w_box * h_box
                ovr = inter / (areas[i] + areas[order[1:]] - inter)

                inds = np.where(ovr <= self.nms_threshold)[0]
                order = order[inds + 1]

            bboxes = bboxes[keep]
            scores = scores[keep]
            kpss = kpss[keep]

            results = []
            for i in range(len(bboxes)):
                bx1, by1, bx2, by2 = bboxes[i]
                
                # Bounding box dimensions
                box_w = bx2 - bx1
                box_h = by2 - by1

                # Dynamic padding (20% horizontal, 25% vertical) for AWS Rekognition context
                pad_x = box_w * 0.20
                pad_y = box_h * 0.25

                crop_x1 = max(0, int(bx1 - pad_x))
                crop_y1 = max(0, int(by1 - pad_y))
                crop_x2 = min(img_w, int(bx2 + pad_x))
                crop_y2 = min(img_h, int(by2 + pad_y))

                face_crop = img[crop_y1:crop_y2, crop_x1:crop_x2]
                if face_crop.size == 0:
                    continue

                # Encode crop as high-quality JPEG
                _, buffer = cv2.imencode('.jpg', face_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                crop_bytes = buffer.tobytes()

                # Relative bounding box in [0, 1] range for API contract
                rel_box = {
                    "x": max(0.0, min(1.0, float(bx1 / img_w))),
                    "y": max(0.0, min(1.0, float(by1 / img_h))),
                    "w": max(0.0, min(1.0, float(box_w / img_w))),
                    "h": max(0.0, min(1.0, float(box_h / img_h)))
                }

                # 5-Point Relative Landmarks: 0:LeftEye, 1:RightEye, 2:Nose, 3:LeftMouth, 4:RightMouth
                rel_landmarks = []
                for pt in kpss[i]:
                    rel_landmarks.append({
                        "x": max(0.0, min(1.0, float(pt[0] / img_w))),
                        "y": max(0.0, min(1.0, float(pt[1] / img_h)))
                    })

                # Environmental Quality Analysis (Brightness & Blur)
                try:
                    gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    brightness = float(np.mean(gray_crop))
                    blur_val = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())

                    # FFT Anti-Spoofing: high frequency grid detection
                    f_transform = np.fft.fft2(gray_crop)
                    f_shift = np.fft.fftshift(f_transform)
                    magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1e-8)
                    ch, cw = gray_crop.shape
                    cy, cx = ch // 2, cw // 2
                    magnitude_spectrum[max(0, cy - 10):cy + 10, max(0, cx - 10):cx + 10] = 0
                    fft_max_hf = float(np.max(magnitude_spectrum))
                except Exception:
                    brightness, blur_val, fft_max_hf = 100.0, 100.0, 0.0

                results.append({
                    "box": rel_box,
                    "landmarks": rel_landmarks,
                    "bytes": crop_bytes,
                    "crop_bgr": face_crop,
                    "confidence": float(scores[i][0]),
                    "brightness": brightness,
                    "blur": blur_val,
                    "fft_max_hf": fft_max_hf
                })

            return results

        except Exception as e:
            print(f"[SCRFD] Face Detection Error: {e}")
            return []

# Singleton detector instance for zero per-frame initialization overhead
_detector_instance = SCRFDFaceDetector()

def detect_faces_crowd(image_bytes):
    """Primary crowd face detection entry point used across tracking and registration."""
    return _detector_instance.detect_faces(image_bytes)

# Backward-compatibility aliases
detect_faces_ultra = detect_faces_crowd
detect_faces_local = detect_faces_crowd
