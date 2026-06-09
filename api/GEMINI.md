🧠 SUB-CONTEXT: API ROUTING LAYER

# Core Identity
This directory handles the High-Frequency WebSocket ingestion loop.

# Strict Rules for AI Agents Editing This Folder
- NEVER block the event loop. Always use `asyncio.to_thread` when calling functions from the `services/` layer (e.g., face detection, AWS calls).
- State is managed per-connection. When modifying logic, ensure it utilizes the `trackers[websocket]` instance so multiple cameras don't overwrite each other's data.
- Payload Optimization: Avoid sending raw Base64 image data back to the client unless strictly requested via a debug flag. Use JSON coordinates (`x, y, w, h`) to instruct the client canvas.
- Error Handling: A crashed frame should NEVER crash the WebSocket. Wrap all frame-processing logic in `try/except` and log cleanly.