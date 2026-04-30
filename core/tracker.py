import math
import collections

class CentroidTracker:
    def __init__(self, max_disappeared=15, max_distance=0.15):
        """
        max_disappeared: frames to keep a face alive after it leaves view.
        max_distance: maximum Euclidean distance between centroids to be considered the same face (normalized 0-1).
        """
        self.next_object_id = 0
        self.objects = collections.OrderedDict()  # id: {"centroid": (x, y), "box": (x,y,w,h), "name": "Scanning...", "aws_calls": 0, "aws_status": "unknown"}
        self.disappeared = collections.OrderedDict() # id: frames_disappeared
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def register(self, centroid, box):
        # Register a new face with full challenge state machine fields
        self.objects[self.next_object_id] = {
            "centroid": centroid,
            "box": box,
            "name": "Scanning...",
            "aws_calls": 0,
            "aws_status": "unknown",
            "score": 0.0,
            "landmarks_history": [],
            "liveness": "pending",
            # --- Challenge-Response Liveness State Machine ---
            "spoof_streak": 0,           # consecutive frames detected as spoof
            "challenge_state": None,     # None | "active" | "verified_real" | "verified_spoof"
            "challenge_instruction": None, # "LEFT" | "RIGHT" | "UP" | "DOWN"
            "challenge_baseline": None,  # (nose_x, nose_y) captured at challenge start
            "challenge_compliance_frames": 0  # consecutive frames compliance is detected
        }
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def deregister(self, object_id):
        # Remove tracking history
        del self.objects[object_id]
        del self.disappeared[object_id]

    def update(self, rects):
        """
        rects: list of dicts {"box": {"x":x, "y":y, "w":w, "h":h}}
        Returns an updated OrderedDict of tracked objects.
        """
        if len(rects) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects

        input_centroids = []
        for i, rect in enumerate(rects):
            b = rect["box"]
            cx = b["x"] + (b["w"] / 2.0)
            cy = b["y"] + (b["h"] / 2.0)
            input_centroids.append((cx, cy))

        if len(self.objects) == 0:
            for i in range(len(input_centroids)):
                self.register(input_centroids[i], rects[i]["box"])
        else:
            object_ids = list(self.objects.keys())
            object_centroids = [obj["centroid"] for obj in self.objects.values()]

            # Compute Euclidean distances
            # Distance matrix: rows=existing objects, cols=new detections
            import numpy as np
            D = np.zeros((len(object_centroids), len(input_centroids)))
            for i, oc in enumerate(object_centroids):
                for j, ic in enumerate(input_centroids):
                    D[i, j] = math.sqrt((oc[0] - ic[0])**2 + (oc[1] - ic[1])**2)

            # Sort rows by minimum distance
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows = set()
            used_cols = set()

            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue
                if D[row, col] > self.max_distance:
                    continue

                object_id = object_ids[row]
                self.objects[object_id]["centroid"] = input_centroids[col]
                self.objects[object_id]["box"] = rects[col]["box"]
                self.disappeared[object_id] = 0
                
                # Update landmarks history and compute liveness
                # Immediate FFT Rejection for Video Spoofing
                if rects[col].get("fft_max_hf", 0) > 250:
                    self.objects[object_id]["liveness"] = "spoof"
                    print(f"[AGI SHIELD] 🛑 Digital Screen / Video Replay detected! (FFT Peak: {rects[col].get('fft_max_hf'):.2f})")
                    
                if "landmarks" in rects[col] and len(rects[col]["landmarks"]) > 0:
                    lm = rects[col]["landmarks"]
                    b = rects[col]["box"]
                    norm_lm = []
                    for pt in lm:
                        nx = (pt["x"] - b["x"]) / (b["w"] + 1e-6)
                        ny = (pt["y"] - b["y"]) / (b["h"] + 1e-6)
                        norm_lm.append((nx, ny))
                    
                    # 3D Parallax Calculation & Center of Mass Drift
                    if len(norm_lm) >= 3:
                        re_x, re_y = norm_lm[0] # Right Eye
                        le_x, le_y = norm_lm[1] # Left Eye
                        nose_x, nose_y = norm_lm[2] # Nose Tip
                        
                        dist_left = math.sqrt((nose_x - le_x)**2 + (nose_y - le_y)**2)
                        dist_right = math.sqrt((nose_x - re_x)**2 + (nose_y - re_y)**2)
                        
                        ratio = dist_left / (dist_right + 1e-6)
                        
                        # Store both the ratio and the normalized nose X coordinate (Drift)
                        self.objects[object_id]["landmarks_history"].append((ratio, nose_x))
                        
                    if len(self.objects[object_id]["landmarks_history"]) > 15:
                        self.objects[object_id]["landmarks_history"].pop(0)
                        
                    hist = self.objects[object_id]["landmarks_history"]
                    if len(hist) >= 10:
                        ratios = [h[0] for h in hist]
                        nose_xs = [h[1] for h in hist]
                        
                        ratio_variance = float(np.var(ratios))
                        nose_drift = float(np.var(nose_xs))
                        
                        # CONTINUOUS EVALUATION (No "pending" lock)
                        # Threshold 0.0002 filters out MediaPipe AI Jitter!
                        # Only evaluate if NOT currently in an active challenge
                        if self.objects[object_id]["challenge_state"] != "active":
                            if ratio_variance < 0.0002 and nose_drift < 0.00005:
                                self.objects[object_id]["liveness"] = "spoof"
                                self.objects[object_id]["spoof_streak"] += 1
                                print(f"[AGI SHIELD] 🛑 2D Photo Suspected! (Parallax: {ratio_variance:.6f}, Drift: {nose_drift:.6f}) Streak: {self.objects[object_id]['spoof_streak']}")
                            else:
                                self.objects[object_id]["liveness"] = "real"
                                self.objects[object_id]["spoof_streak"] = 0  # Reset streak on real frame

                        # --- Challenge Compliance Check (runs every frame if challenge is active) ---
                        if self.objects[object_id]["challenge_state"] == "active" and self.objects[object_id]["challenge_baseline"] is not None:
                            baseline_nx, baseline_ny = self.objects[object_id]["challenge_baseline"]
                            instruction = self.objects[object_id]["challenge_instruction"]
                            complied = False
                            if instruction == "LEFT"  and nose_x < baseline_nx - 0.07: complied = True
                            elif instruction == "RIGHT" and nose_x > baseline_nx + 0.07: complied = True
                            elif instruction == "UP"   and nose_y < baseline_ny - 0.06: complied = True
                            elif instruction == "DOWN"  and nose_y > baseline_ny + 0.06: complied = True

                            if complied:
                                self.objects[object_id]["challenge_compliance_frames"] += 1
                                # Require 5 consecutive compliant frames to confirm human
                                if self.objects[object_id]["challenge_compliance_frames"] >= 5:
                                    self.objects[object_id]["challenge_state"] = "verified_real"
                                    self.objects[object_id]["liveness"] = "real"
                                    self.objects[object_id]["spoof_streak"] = 0
                                    self.objects[object_id]["aws_status"] = "unknown"  # Re-open AWS gate
                                    self.objects[object_id]["aws_calls"] = 0
                                    print(f"[CHALLENGE] ✅ Face {object_id} passed challenge: {instruction}")
                            else:
                                # Decay compliance frames if not actively complying
                                self.objects[object_id]["challenge_compliance_frames"] = max(0, self.objects[object_id]["challenge_compliance_frames"] - 1)

                used_rows.add(row)
                used_cols.add(col)

            # Check unused rows (disappeared)
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            # Check unused cols (new detections)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)
            for col in unused_cols:
                self.register(input_centroids[col], rects[col]["box"])
                # Add initial landmarks properly formatted as (ratio, nose_x)
                if "landmarks" in rects[col] and len(rects[col]["landmarks"]) >= 3:
                    lm = rects[col]["landmarks"]
                    b = rects[col]["box"]
                    
                    re_nx = (lm[0]["x"] - b["x"]) / (b["w"] + 1e-6)
                    re_ny = (lm[0]["y"] - b["y"]) / (b["h"] + 1e-6)
                    le_nx = (lm[1]["x"] - b["x"]) / (b["w"] + 1e-6)
                    le_ny = (lm[1]["y"] - b["y"]) / (b["h"] + 1e-6)
                    nose_nx = (lm[2]["x"] - b["x"]) / (b["w"] + 1e-6)
                    nose_ny = (lm[2]["y"] - b["y"]) / (b["h"] + 1e-6)

                    dist_left = math.sqrt((nose_nx - le_nx)**2 + (nose_ny - le_ny)**2)
                    dist_right = math.sqrt((nose_nx - re_nx)**2 + (nose_ny - re_ny)**2)
                    ratio = dist_left / (dist_right + 1e-6)
                    
                    self.objects[self.next_object_id - 1]["landmarks_history"].append((ratio, nose_nx))

        return self.objects
