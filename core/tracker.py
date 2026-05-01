import math
import time
import collections

class CentroidTracker:
    def __init__(self, max_disappeared=15, max_distance=0.15):
        """
        max_disappeared: frames to keep a face alive after it leaves view.
        max_distance: maximum Euclidean distance (normalized 0-1) to match centroids.
        """
        self.next_object_id = 0
        self.objects = collections.OrderedDict()
        self.disappeared = collections.OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def register(self, centroid, box):
        """Register a new face with all required state fields."""
        self.objects[self.next_object_id] = {
            # --- Core Tracking ---
            "centroid": centroid,
            "box": box,
            "name": "Scanning...",
            "aws_calls": 0,
            "aws_status": "unknown",
            "score": 0.0,
            # --- Liveness (MiniFASNet Score Accumulator) ---
            "liveness": "pending",          # pending | real | spoof
            "liveness_scores": [],          # rolling window of MiniFASNet scores
            "tracked_since": time.time(),   # timestamp of first detection
            # --- Challenge-Response State Machine ---
            "spoof_streak": 0,
            "challenge_state": None,        # None | active | verified_real | verified_spoof
            "challenge_instruction": None,  # LEFT | RIGHT | UP | DOWN
            "challenge_baseline": None,     # (nose_x, nose_y) at challenge start
            "challenge_compliance_frames": 0,
            # --- Landmark History (for challenge compliance math) ---
            "landmarks_history": [],
        }
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def deregister(self, object_id):
        del self.objects[object_id]
        del self.disappeared[object_id]

    def inject_liveness_score(self, object_id: int, score: float):
        """
        Called by websocket.py after async MiniFASNet inference.
        Accumulates up to 5 scores, then makes a hard liveness decision.

        score: 0.0 = SPOOF | 1.0 = REAL (from MiniFASNet)
        """
        if object_id not in self.objects:
            return

        obj = self.objects[object_id]

        # Don't overwrite a verified challenge result
        if obj["challenge_state"] in ("verified_real", "active"):
            return

        scores = obj["liveness_scores"]
        scores.append(score)

        # Keep a rolling window of 5 frames
        if len(scores) > 5:
            scores.pop(0)

        # Only make a hard verdict after accumulating 3+ scores
        if len(scores) >= 3:
            avg = sum(scores) / len(scores)
            if avg >= 0.82:
                obj["liveness"] = "real"
                obj["spoof_streak"] = 0
                print(f"[LIVENESS] ✅ Face {object_id} REAL (avg={avg:.3f})")
            else:
                obj["liveness"] = "spoof"
                obj["spoof_streak"] += 1
                print(f"[LIVENESS] 🛑 Face {object_id} SPOOF (avg={avg:.3f}) Streak={obj['spoof_streak']}")

    def update(self, rects):
        """
        rects: list of dicts {box, landmarks, bytes, brightness, blur, fft_max_hf}
        Returns the updated OrderedDict of tracked objects.
        """
        if len(rects) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects

        input_centroids = []
        for rect in rects:
            b = rect["box"]
            cx = b["x"] + (b["w"] / 2.0)
            cy = b["y"] + (b["h"] / 2.0)
            input_centroids.append((cx, cy))

        if len(self.objects) == 0:
            for i in range(len(input_centroids)):
                self.register(input_centroids[i], rects[i]["box"])
        else:
            import numpy as np
            object_ids = list(self.objects.keys())
            object_centroids = [obj["centroid"] for obj in self.objects.values()]

            D = np.zeros((len(object_centroids), len(input_centroids)))
            for i, oc in enumerate(object_centroids):
                for j, ic in enumerate(input_centroids):
                    D[i, j] = math.sqrt((oc[0] - ic[0])**2 + (oc[1] - ic[1])**2)

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

                # Update landmark history for challenge compliance math
                if "landmarks" in rects[col] and len(rects[col]["landmarks"]) >= 3:
                    lm = rects[col]["landmarks"]
                    b  = rects[col]["box"]
                    nose_nx = (lm[2]["x"] - b["x"]) / (b["w"] + 1e-6)
                    nose_ny = (lm[2]["y"] - b["y"]) / (b["h"] + 1e-6)

                    # Challenge compliance check (runs every frame when challenge is active)
                    if (self.objects[object_id]["challenge_state"] == "active"
                            and self.objects[object_id]["challenge_baseline"] is not None):
                        bx, by = self.objects[object_id]["challenge_baseline"]
                        instruction = self.objects[object_id]["challenge_instruction"]
                        complied = False
                        if instruction == "LEFT"  and nose_nx < bx - 0.07: complied = True
                        elif instruction == "RIGHT" and nose_nx > bx + 0.07: complied = True
                        elif instruction == "UP"   and nose_ny < by - 0.06: complied = True
                        elif instruction == "DOWN"  and nose_ny > by + 0.06: complied = True

                        if complied:
                            self.objects[object_id]["challenge_compliance_frames"] += 1
                            if self.objects[object_id]["challenge_compliance_frames"] >= 5:
                                self.objects[object_id]["challenge_state"] = "verified_real"
                                self.objects[object_id]["liveness"] = "real"
                                self.objects[object_id]["spoof_streak"] = 0
                                self.objects[object_id]["aws_status"] = "unknown"
                                self.objects[object_id]["aws_calls"] = 0
                                self.objects[object_id]["liveness_scores"] = [1.0, 1.0, 1.0]
                                print(f"[CHALLENGE] ✅ Face {object_id} passed: {instruction}")
                        else:
                            self.objects[object_id]["challenge_compliance_frames"] = max(
                                0, self.objects[object_id]["challenge_compliance_frames"] - 1
                            )

                    hist = self.objects[object_id]["landmarks_history"]
                    hist.append((nose_nx, nose_ny))
                    if len(hist) > 15:
                        hist.pop(0)

                # FFT immediate screen detection (keep as Layer 1 fast filter)
                if rects[col].get("fft_max_hf", 0) > 250:
                    self.objects[object_id]["liveness"] = "spoof"
                    self.objects[object_id]["spoof_streak"] += 1
                    print(f"[FFT SHIELD] 🛑 Digital screen detected! (FFT={rects[col].get('fft_max_hf'):.1f})")

                used_rows.add(row)
                used_cols.add(col)

            unused_rows = set(range(D.shape[0])).difference(used_rows)
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)

            unused_cols = set(range(D.shape[1])).difference(used_cols)
            for col in unused_cols:
                self.register(input_centroids[col], rects[col]["box"])

        return self.objects
