🧠 SUB-CONTEXT: CORE LOGIC & STATE

# Core Identity
This directory is the nervous system (State, Config, Tracker Math). 

# Strict Rules for AI Agents Editing This Folder
- `config.py`: Never hardcode logic thresholds. All thresholds (MATCH_THRESHOLD, COOL_DOWN) must remain configurable constants.
- `state.py`: Be cautious of memory leaks. The dictionaries `last_seen` and `temporal_memory` grow over time. If you modify them, implement garbage collection (timestamp checks).
- `tracker.py`: Only use `numpy` or standard math for tracking logic. Do not introduce PyTorch/Tensorflow dependencies here; keep it ultra-lightweight CPU math. Ensure Euclidean distance is normalized against box width/height if needed for perspective invariance.