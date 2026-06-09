🧠 SUB-CONTEXT: FRONTEND PRESENTATION

# Core Identity
This directory controls the Vibe, HUD, and Canvas rendering.

# Strict Rules for AI Agents Editing This Folder
- Performance: The `renderLoop()` in `app.js` fires up to 60 times a second. NEVER execute heavy DOM manipulations (like innerHTML) inside the loop unless the data has actually changed.
- Rendering: Use the `LERP_FACTOR` to smooth out bounding box tracking. Do not snap boxes to absolute coordinates instantly.
- Theme: Maintain the "Cyberpunk / Glassmorphism" aesthetic. Use Tailwind `bg-black/60`, `backdrop-blur-sm`, and `brand-cyan` accents.
- Connection Drops: The WebSocket logic must always attempt `Exponential Backoff Reconnection` if the server goes offline.