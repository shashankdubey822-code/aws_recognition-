🧠 SUB-CONTEXT: AI SERVICES LAYER

# Core Identity
This is the "Brain" folder. It wraps external APIs (AWS) and local AI (MediaPipe).

# Strict Rules for AI Agents Editing This Folder
- Single Responsibility: Each file does ONE thing. Do not mix face detection logic into `aws_client.py`.
- Liveness Engine (`liveness_engine.py`): This relies on 3D geometry (FaceMesh). Do not break the `Scale-Invariant Z-Depth Variance` math by changing camera FOV assumptions.
- Fail-Safe Cloud: `aws_client.py` MUST gracefully catch `botocore.exceptions.ClientError`. If AWS goes down or rate limits, the app must not crash; it should fail gracefully to local-only tracking.
- Memory: When dealing with OpenCV `cv2` or `numpy` arrays, ensure arrays are garbage collected (avoid large global cache buffers of images).