const video = document.getElementById('videoElement');
const canvas = document.getElementById('canvasElement');
const ctx = canvas.getContext('2d', { willReadFrequently: true });
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const statusBadge = document.getElementById('status-badge');
const attendanceList = document.getElementById('attendance-list');
const confirmedList = document.getElementById('confirmed-list');
const terminalLogs = document.getElementById('terminal-logs');
const debugCrops = document.getElementById('debug-crops');
const cropCount = document.getElementById('crop-count');

// --- REGISTRATION UI ELEMENTS ---
const addStudentBtn = document.getElementById('add-student-btn');
const modalBackdrop = document.getElementById('modal-backdrop');
const cancelBtn = document.getElementById('cancel-btn');
const startScanBtn = document.getElementById('start-scan-btn');
const studentNameInput = document.getElementById('student-name-input');
const regOverlay = document.getElementById('reg-overlay');
const regInstruction = document.getElementById('reg-instruction');
const regSubtext = document.getElementById('reg-subtext');

const cameraSelect = document.getElementById('camera-select');

let ws;
let isProcessing = false;
let currentStream = null;
let isFrontCamera = true;
let availableCameras = [];
let frameCount = 0;
let lastFpsTime = Date.now();
let reconnectAttempts = 0;
let pingInterval;

let currentlyVisible = {};
let confirmedPeople = new Set(); 
const VISIBILITY_TIMEOUT_MS = 3000;

// --- ADVANCED GAMIFIED REGISTRATION STATE ---
let isRegistering = false;
const REQUIRED_REG_FRAMES = 20; 
let regProgress = 0;
let regPulseAngle = 0;
let flashAlpha = 0; 
let targetX = 0, targetY = 0;
let currentDotX = 0, currentDotY = 0;

// --- ADVANCED SMOOTH TRACKING STATE ---
let trackedFaces = {}; 
const LERP_FACTOR = 0.3; 
const BOX_FADEOUT_MS = 2000; 

// --- SHARED UI STATE ---
let lastSpeechMsg = "";
let lastSpeechTime = 0;

// --- CHALLENGE-RESPONSE STATE ---
let activeChallenges = {}; // face_id -> { instruction, deadline, element }

// --- TOAST NOTIFICATION SYSTEM ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    
    // AGI Fix: Enforce strict First-In-First-Out (FIFO) queue of max 3 toasts to prevent screen spam
    while (container.children.length >= 3) {
        container.removeChild(container.firstChild);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = '';
    if (type === 'error') icon = '❌';
    else if (type === 'success') icon = '✅';
    else if (type === 'warning') icon = '⚠️';
    else icon = 'ℹ️';

    toast.innerHTML = `
        <div class="text-xl">${icon}</div>
        <div class="flex-1">
            <h4 class="text-sm font-bold capitalize text-white">${type}</h4>
            <p class="text-xs text-slate-300">${message}</p>
        </div>
    `;
    
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease-out reverse forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- HACKER TERMINAL ---
function logToTerminal(msg, type = 'info') {
    const div = document.createElement('div');
    const time = new Date().toISOString().split('T')[1].slice(0, 12);
    
    let colorClass = 'text-slate-300';
    let prefix = '[-]';
    if (type === 'error' || msg.includes('ERROR')) { colorClass = 'text-red-400 font-bold'; prefix = '[!]'; }
    else if (type === 'success' || msg.includes('✅')) { colorClass = 'text-emerald-400 font-bold'; prefix = '[+]'; }
    else if (msg.includes('📡')) { colorClass = 'text-brand-cyan'; prefix = '[~]'; }

    div.innerHTML = `<span class="text-slate-500 opacity-50">[${time}]</span> <span class="${colorClass}">${prefix} ${msg.replace(/✅|❌|📡/g, '')}</span>`;
    terminalLogs.appendChild(div);
    if (terminalLogs.children.length > 50) terminalLogs.removeChild(terminalLogs.firstChild);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
}

// Calculate dynamic WebSocket URL
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;

// --- REGISTRATION HANDLERS ---
addStudentBtn.addEventListener('click', () => {
    modalBackdrop.classList.remove('hidden');
    studentNameInput.value = '';
    studentNameInput.focus();
});

cancelBtn.addEventListener('click', () => {
    modalBackdrop.classList.add('hidden');
});

startScanBtn.addEventListener('click', () => {
    const name = studentNameInput.value.trim().replace(/ /g, '_').replace(/[^a-zA-Z0-9_.\-:]/g, '_');
    if (!name) { showToast("Invalid Identity Name", "error"); return; }
    
    isRegistering = true;
    regProgress = 0;
    targetX = overlayCanvas.width / 2;
    targetY = overlayCanvas.height / 2;
    currentDotX = targetX;
    currentDotY = targetY;

    modalBackdrop.classList.add('hidden');
    regOverlay.classList.remove('hidden');
    
    regInstruction.textContent = "INITIALIZING 3D SCAN";
    regSubtext.textContent = "Align face within target vector...";
    
    trackedFaces = {};
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    ws.send(JSON.stringify({ type: 'start_registration', name: name }));
    logToTerminal(`Initiated biometric mapping for ${name}`, 'info');
});

// --- AUDIO ENGINE ---
let audioCtx;
function initAudio() { if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
function playTone(freq, type, duration, vol=0.1) {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(vol, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
}

function speakWarning(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const msg = new SpeechSynthesisUtterance(text);
        msg.rate = 0.9;
        msg.pitch = 0.5;
        msg.volume = 1.0;
        window.speechSynthesis.speak(msg);
    }
}

// --- CHALLENGE-RESPONSE UI FUNCTIONS ---
const DIRECTION_ARROWS = { LEFT: '←', RIGHT: '→', UP: '↑', DOWN: '↓' };

function showChallengeOverlay(faceId, instruction) {
    hideChallengeOverlay(faceId); // Remove any existing overlay first
    
    const container = document.getElementById('video-container');
    const panel = document.createElement('div');
    panel.id = `challenge-overlay-${faceId}`;
    panel.style.cssText = `
        position: absolute; inset: 0; z-index: 30;
        background: rgba(220, 38, 38, 0.15);
        border: 3px solid rgba(220, 38, 38, 0.8);
        border-radius: 1rem;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        backdrop-filter: blur(2px);
        animation: challengePulse 0.8s ease-in-out infinite alternate;
    `;
    
    const deadline = Date.now() + 15000;
    activeChallenges[faceId].element = panel;
    activeChallenges[faceId].deadline = deadline;

    panel.innerHTML = `
        <div style="text-align:center; padding: 1rem;">
            <div style="font-family:'Orbitron',monospace; font-size:13px; color:#fca5a5; letter-spacing:0.2em; margin-bottom:8px;">⚠ IDENTITY CHALLENGE REQUIRED</div>
            <div style="font-family:'Orbitron',monospace; font-size:48px; color:#ff4444; margin: 8px 0; text-shadow: 0 0 20px rgba(255,68,68,0.8);">${DIRECTION_ARROWS[instruction]}</div>
            <div style="font-family:'Orbitron',monospace; font-size:20px; font-weight:900; color:white; letter-spacing:0.15em;">TURN ${instruction}</div>
            <div id="challenge-countdown-${faceId}" style="font-family:'Orbitron',monospace; font-size:13px; color:#fca5a5; margin-top:10px;">15s remaining</div>
        </div>
    `;
    container.appendChild(panel);

    // Add CSS animation
    if (!document.getElementById('challenge-style')) {
        const style = document.createElement('style');
        style.id = 'challenge-style';
        style.textContent = `
            @keyframes challengePulse {
                from { border-color: rgba(220,38,38,0.6); box-shadow: 0 0 10px rgba(220,38,38,0.3); }
                to   { border-color: rgba(220,38,38,1.0); box-shadow: 0 0 30px rgba(220,38,38,0.8); }
            }
            @keyframes challengePass {
                from { border-color: rgba(16,185,129,0.4); }
                to   { border-color: rgba(16,185,129,1.0); box-shadow: 0 0 40px rgba(16,185,129,0.8); }
            }
        `;
        document.head.appendChild(style);
    }

    // Countdown timer
    const tick = setInterval(() => {
        const remaining = Math.max(0, Math.ceil((activeChallenges[faceId]?.deadline - Date.now()) / 1000));
        const el = document.getElementById(`challenge-countdown-${faceId}`);
        if (el) el.textContent = `${remaining}s remaining`;
        if (remaining <= 0) clearInterval(tick);
    }, 500);
    activeChallenges[faceId].tickInterval = tick;
}

function updateChallengeOverlay(faceId, result) {
    const panel = activeChallenges[faceId]?.element;
    if (!panel) return;
    if (result === 'passed') {
        panel.style.background = 'rgba(16, 185, 129, 0.2)';
        panel.style.borderColor = 'rgba(16, 185, 129, 0.9)';
        panel.style.animation = 'challengePass 0.5s ease-in-out infinite alternate';
        panel.innerHTML = `
            <div style="text-align:center; padding: 1rem;">
                <div style="font-size: 56px;">✅</div>
                <div style="font-family:'Orbitron',monospace; font-size:20px; font-weight:900; color:#10b981; letter-spacing:0.1em; margin-top:10px;">LIVENESS CONFIRMED</div>
                <div style="font-family:'Orbitron',monospace; font-size:11px; color:#6ee7b7; margin-top:6px;">Proceeding to identity verification...</div>
            </div>
        `;
    } else {
        panel.style.background = 'rgba(127, 0, 0, 0.5)';
        panel.style.animation = 'none';
        panel.innerHTML = `
            <div style="text-align:center; padding: 1rem;">
                <div style="font-size: 56px;">❌</div>
                <div style="font-family:'Orbitron',monospace; font-size:20px; font-weight:900; color:#ff4444; letter-spacing:0.1em; margin-top:10px;">SPOOF CONFIRMED</div>
                <div style="font-family:'Orbitron',monospace; font-size:11px; color:#fca5a5; margin-top:6px;">Access Denied. Entity Logged.</div>
            </div>
        `;
    }
}

function hideChallengeOverlay(faceId) {
    const ch = activeChallenges[faceId];
    if (ch) {
        if (ch.tickInterval) clearInterval(ch.tickInterval);
        if (ch.element) ch.element.remove();
    }
    delete activeChallenges[faceId];
}

// --- CINEMATIC HUD RENDERING ---
function updateTargetFaces(faces) {
    const now = Date.now();
    if (!faces) return;

    faces.forEach((face) => {
        if (!face.box) return;
        const id = face.id; // Unique tracker ID from backend!
        
        if (!trackedFaces[id]) {
            trackedFaces[id] = {
                currentBox: { ...face.box },
                targetBox: { ...face.box },
                lastUpdate: now,
                ...face
            };
        } else {
            trackedFaces[id].targetBox = { ...face.box };
            trackedFaces[id].lastUpdate = now;
            trackedFaces[id].name = face.name;
            trackedFaces[id].score = face.score;
            trackedFaces[id].status = face.status;
            if(face.crop) trackedFaces[id].crop = face.crop;
        }
    });
}

function drawHighTechCorners(ctx, x, y, w, h, color, alpha) {
    const len = Math.min(w, h) * 0.15; 
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineCap = 'square';
    
    // Crosshairs
    ctx.beginPath();
    ctx.moveTo(x - 10, y + h/2); ctx.lineTo(x + 10, y + h/2);
    ctx.moveTo(x + w/2, y - 10); ctx.lineTo(x + w/2, y + 10);
    ctx.moveTo(x + w + 10, y + h/2); ctx.lineTo(x + w - 10, y + h/2);
    ctx.moveTo(x + w/2, y + h + 10); ctx.lineTo(x + w/2, y + h - 10);
    ctx.stroke();

    // Corners
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x, y + len); ctx.lineTo(x, y); ctx.lineTo(x + len, y);
    ctx.moveTo(x + w - len, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + len);
    ctx.moveTo(x + w, y + h - len); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w - len, y + h);
    ctx.moveTo(x + len, y + h); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h - len);
    ctx.stroke();
    
    // Fill
    ctx.globalAlpha = alpha * 0.1;
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
    
    ctx.globalAlpha = 1.0; 
}

function drawSmoothFaces() {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    const now = Date.now();
    
    for (const id in trackedFaces) {
        const face = trackedFaces[id];
        const age = now - face.lastUpdate;
        
        if (age > BOX_FADEOUT_MS) {
            delete trackedFaces[id];
            continue;
        }
        
        face.currentBox.x += (face.targetBox.x - face.currentBox.x) * LERP_FACTOR;
        face.currentBox.y += (face.targetBox.y - face.currentBox.y) * LERP_FACTOR;
        face.currentBox.w += (face.targetBox.w - face.currentBox.w) * LERP_FACTOR;
        face.currentBox.h += (face.targetBox.h - face.currentBox.h) * LERP_FACTOR;

        let { x, y, w, h } = face.currentBox;
        // Apply horizontal mirror flip ONLY if using the front/user camera
        const renderX = isFrontCamera ? (overlayCanvas.width - x - w) : x;
        
        let color = '#ef4444'; // Red
        let alpha = age > 200 ? Math.max(0, 1 - ((age - 200) / 1000)) : 1;
        
        // AGI FIX: If match is successful, the massive target box shrinks down to a small, sleek marker 
        // falling back to capturing the original full-screen size visually.
        if (face.status === 'match') {
            color = '#10b981'; // Green
            overlayCtx.globalAlpha = alpha;
            
            // Minimalist verified marker
            overlayCtx.beginPath();
            overlayCtx.arc(renderX + w/2, y + h/2 - 20, 15, 0, Math.PI * 2);
            overlayCtx.fillStyle = color;
            overlayCtx.fill();
            overlayCtx.lineWidth = 2;
            overlayCtx.strokeStyle = 'white';
            overlayCtx.stroke();
            
            // Checkmark inside the marker
            overlayCtx.beginPath();
            overlayCtx.moveTo(renderX + w/2 - 5, y + h/2 - 20);
            overlayCtx.lineTo(renderX + w/2 - 1, y + h/2 - 15);
            overlayCtx.lineTo(renderX + w/2 + 6, y + h/2 - 25);
            overlayCtx.strokeStyle = 'white';
            overlayCtx.lineWidth = 3;
            overlayCtx.lineCap = 'round';
            overlayCtx.stroke();

            // Label
            overlayCtx.fillStyle = 'rgba(0,0,0,0.8)';
            const labelText = `${face.name.replace(/_/g, ' ')}`;
            overlayCtx.font = 'bold 11px "Orbitron", monospace';
            const textWidth = overlayCtx.measureText(labelText).width;
            overlayCtx.fillRect(renderX + w/2 - textWidth/2 - 10, y + h/2 + 5, textWidth + 20, 20);
            
            overlayCtx.fillStyle = color;
            overlayCtx.fillText(labelText, renderX + w/2 - textWidth/2, y + h/2 + 19);
            overlayCtx.globalAlpha = 1.0;
            continue;
        }
        
        if (face.status === 'verifying') color = '#00d2ff'; // Cyan
        else if (face.status === 'spoof') color = '#ff0000'; // Pure Red
        
        if (face.status === 'spoof' && Date.now() % 500 < 250) alpha = 0.2; // Flash effect
        
        drawHighTechCorners(overlayCtx, renderX, y, w, h, color, alpha);
        
        // Target Box HUD Label
        overlayCtx.globalAlpha = alpha;
        let labelText = '';
        if (face.status === 'verifying') labelText = 'SCANNING...';
        else if (face.status === 'spoof') labelText = 'SPOOF DETECTED';
        else labelText = `${face.name.replace(/_/g, ' ')} [${(face.score || 0).toFixed(1)}%]`;
        
        overlayCtx.font = 'bold 12px "Orbitron", monospace';
        const textWidth = overlayCtx.measureText(labelText).width;
        
        overlayCtx.fillStyle = 'rgba(0,0,0,0.8)';
        overlayCtx.fillRect(renderX, y - 25, textWidth + 20, 20);
        
        overlayCtx.fillStyle = color;
        overlayCtx.fillText(labelText, renderX + 10, y - 11);
        
        // Decorator lines
        overlayCtx.beginPath();
        overlayCtx.moveTo(renderX, y - 5);
        overlayCtx.lineTo(renderX - 20, y - 25);
        overlayCtx.lineTo(renderX - 20, y - 50);
        overlayCtx.strokeStyle = color;
        overlayCtx.lineWidth = 1;
        overlayCtx.stroke();

        overlayCtx.globalAlpha = 1.0;
    }
}

function drawGamifiedScanner() {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    if (flashAlpha > 0) {
        overlayCtx.fillStyle = `rgba(0, 210, 255, ${flashAlpha})`;
        overlayCtx.fillRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        flashAlpha -= 0.05;
    }
    
    currentDotX += (targetX - currentDotX) * 0.1;
    currentDotY += (targetY - currentDotY) * 0.1;

    regPulseAngle += 0.1;
    const pulseRadius = 40 + Math.sin(regPulseAngle) * 10;
    
    // Core Reticle
    overlayCtx.beginPath();
    overlayCtx.arc(currentDotX, currentDotY, pulseRadius, 0, Math.PI * 2);
    overlayCtx.fillStyle = 'rgba(0, 210, 255, 0.2)';
    overlayCtx.fill();
    overlayCtx.strokeStyle = 'rgba(0, 210, 255, 0.8)';
    overlayCtx.lineWidth = 2;
    overlayCtx.setLineDash([5, 10]);
    overlayCtx.stroke();
    overlayCtx.setLineDash([]);

    // Center dot
    overlayCtx.shadowBlur = 15;
    overlayCtx.shadowColor = '#00d2ff';
    overlayCtx.beginPath();
    overlayCtx.arc(currentDotX, currentDotY, 8, 0, Math.PI * 2);
    overlayCtx.fillStyle = '#fff';
    overlayCtx.fill();
    overlayCtx.shadowBlur = 0;

    // Progress Arc
    const progressPct = regProgress / REQUIRED_REG_FRAMES;
    if (progressPct > 0) {
        overlayCtx.beginPath();
        overlayCtx.arc(currentDotX, currentDotY, 60, -Math.PI / 2, (-Math.PI / 2) + (Math.PI * 2 * progressPct));
        overlayCtx.strokeStyle = '#10b981';
        overlayCtx.lineWidth = 4;
        overlayCtx.lineCap = 'round';
        overlayCtx.stroke();
    }
}

function updateDebugCrops(faces) {
    debugCrops.innerHTML = '';
    if (!faces || faces.length === 0) {
        debugCrops.innerHTML = '<div class="text-xs text-slate-600 italic font-mono">Awaiting target...</div>';
        cropCount.textContent = '0';
        return;
    }
    cropCount.textContent = faces.length;

    faces.forEach(face => {
        if (face.crop) {
            const container = document.createElement('div');
            container.className = 'relative flex-shrink-0 animate-slideIn';
            const img = document.createElement('img');
            img.src = face.crop;
            let borderCol = 'border-red-500/50';
            if (face.status === 'match') borderCol = 'border-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]';
            else if (face.status === 'verifying') borderCol = 'border-brand-cyan shadow-[0_0_10px_rgba(0,210,255,0.5)]';
            else if (face.status === 'spoof') borderCol = 'border-red-600 shadow-[0_0_15px_rgba(255,0,0,0.8)] animate-pulse';
            
            img.className = `w-14 h-14 rounded-md border-2 ${borderCol} object-cover`;
            
            const badge = document.createElement('div');
            badge.className = 'absolute bottom-0 left-0 right-0 bg-black/80 text-[8px] text-center py-0.5 truncate text-white font-mono';
            badge.textContent = face.status === 'match' ? 'VERIFIED' : (face.status === 'verifying' ? 'SCANNING' : (face.status === 'spoof' ? 'SPOOF' : 'UNKNOWN'));
            
            container.appendChild(img);
            container.appendChild(badge);
            debugCrops.appendChild(container);
        }
    });
}

// --- WEBSOCKET ENGINE ---
function connectWebSocket() {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
        reconnectAttempts = 0;
        document.getElementById('ws-status').textContent = 'SYSTEM ONLINE';
        document.getElementById('ws-status').className = 'text-sm font-mono text-emerald-400 tracking-wide';
        logToTerminal("WebSocket Connected. Security Core active.", "success");
        showToast("Connected to AI Subsystem", "success");
        pingInterval = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'heartbeat' })); }, 10000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // --- ERROR RECOVERY (CRITICAL FIX) ---
        if (data.type === 'error') {
            isProcessing = false;
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
            return;
        }

        if (data.type === 'intruder_alert') {
            const overlay = document.getElementById('intruder-alert');
            if (overlay) overlay.classList.remove('hidden');
            const img = document.getElementById('intruder-img');
            if (img) img.src = data.image;
            
            initAudio();
            playTone(300, 'square', 1.0, 0.5);
            speakWarning("Security Alert. Unidentified entity detected.");
            logToTerminal(`[WARNING] Intruder Snapshot Captured!`, "error");
            
            setTimeout(() => {
                if (overlay) overlay.classList.add('hidden');
            }, 5000);
            return;
        }

        else if (data.type === 'registration_status') {
            isProcessing = false;

            if (data.progress > regProgress) {
                initAudio();
                playTone(1000, 'sine', 0.1);
                flashAlpha = 0.5;
            }

            regProgress = data.progress;
            regSubtext.textContent = `${data.message}`;

            // AGI Voice Coach: Speak any new instruction
            if (data.message !== lastSpeechMsg && (Date.now() - lastSpeechTime > 3000)) {
                speakWarning(data.message);
                lastSpeechMsg = data.message;
                lastSpeechTime = Date.now();
            }

            if (regProgress < 5) {
                regInstruction.textContent = "Maintain Center Lock";
                targetX = overlayCanvas.width / 2;
            } else if (regProgress >= 5 && regProgress < 12) {
                regInstruction.textContent = "Left Profile Vector";
                targetX = overlayCanvas.width * 0.8;
            } else if (regProgress >= 12 && regProgress < 18) {
                regInstruction.textContent = "Right Profile Vector";
                targetX = overlayCanvas.width * 0.2;
            } else {
                regInstruction.textContent = "Finalizing 3D Mesh...";
                targetX = overlayCanvas.width / 2;
            }

            if (regProgress >= 100 && isRegistering) {
                isRegistering = false;
                isProcessing = false;
                regInstruction.textContent = "Processing Identity...";
                logToTerminal("Uploading Neural Profile to Database...", "info");
            }
        } 
        else if (data.type === 'registration_waiting') {
            isProcessing = false;
            regSubtext.textContent = data.message;
            
            // AGI Voice Coach: Speak any coaching message (Fixes missing UP/DOWN voice)
            if (data.message !== lastSpeechMsg || (Date.now() - lastSpeechTime > 3000)) {
                speakWarning(data.message);
                lastSpeechMsg = data.message;
                lastSpeechTime = Date.now();
            }
        } 
        else if (data.type === 'registration_success') {
            playTone(1200, 'triangle', 0.4, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "success");
            showToast("Identity Registered", "success");
        } 
        else if (data.type === 'registration_error') {
            playTone(200, 'sawtooth', 0.5, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
        }

        else if (data.type === 'attendance') {
            currentlyVisible[data.name] = Date.now();
            // Clear any active challenge for this face when attendance confirmed
            for (const fid in activeChallenges) {
                hideChallengeOverlay(fid);
            }
            renderPresenceList();
            addConfirmedEntry(data.name, data.time);
            showToast(`Clearance Granted: ${data.name.replace(/_/g, ' ')}`, "success");
            playTone(1500, 'sine', 0.1);
            logToTerminal(`Clearance Granted: ${data.name}`, "success");
        }

        // --- CHALLENGE-RESPONSE MESSAGE HANDLERS ---
        else if (data.type === 'challenge') {
            const fid = data.face_id;
            const instruction = data.instruction;
            activeChallenges[fid] = { instruction, deadline: Date.now() + 15000 };

            showChallengeOverlay(fid, instruction);

            // Speak the challenge instruction
            initAudio();
            playTone(440, 'sine', 0.3, 0.15);
            speakWarning(`Security check. Turn your head ${instruction}.`);
            logToTerminal(`[CHALLENGE] Face ${fid}: Turn ${instruction}`, 'warning');
        }

        else if (data.type === 'challenge_passed') {
            const fid = data.face_id;
            if (activeChallenges[fid]) {
                updateChallengeOverlay(fid, 'passed');
                playTone(1200, 'triangle', 0.4, 0.2);
                setTimeout(() => hideChallengeOverlay(fid), 2000);
            }
            logToTerminal(`[CHALLENGE] ✅ Face ${fid} verified as real!`, 'success');
        }

        else if (data.type === 'challenge_failed') {
            const fid = data.face_id;
            if (activeChallenges[fid]) {
                updateChallengeOverlay(fid, 'failed');
                playTone(200, 'sawtooth', 0.8, 0.3);
                speakWarning("Spoof detected. Access denied.");
                setTimeout(() => hideChallengeOverlay(fid), 3000);
            }
            logToTerminal(`[CHALLENGE] ❌ Face ${fid} SPOOF CONFIRMED`, 'error');
        } 
        else if (data.type === 'ready') {
            isProcessing = false;

            if (data.debug) {
                if (Math.random() < 0.1) { // Throttle terminal spam
                    logToTerminal(data.debug, "info");
                }
            }

            if (data.faces && data.faces.length > 0) {
                updateTargetFaces(data.faces);
                if (!isRegistering) updateDebugCrops(data.faces);
                
                data.faces.forEach(face => {
                    if (face.status === 'match') currentlyVisible[face.name] = Date.now();
                });
                renderPresenceList();
            } else {
                trackedFaces = {};
                updateDebugCrops([]);
            }
        }
    };

    ws.onclose = () => {
        isProcessing = false;
        clearInterval(pingInterval);
        document.getElementById('ws-status').textContent = 'CONNECTION LOST';
        document.getElementById('ws-status').className = 'text-sm font-mono text-red-500 tracking-wide animate-pulse';
        showToast("Lost connection to AI Core", "error");
        logToTerminal(`WebSocket disconnected.`, "error");
        
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        setTimeout(connectWebSocket, timeout);
        reconnectAttempts++;
    };
}

function addConfirmedEntry(name, time) {
    if (confirmedPeople.has(name)) return;
    if (confirmedPeople.size === 0) confirmedList.innerHTML = '';
    confirmedPeople.add(name);
    
    const div = document.createElement('div');
    div.className = 'bg-brand-emerald/10 p-3 rounded-xl border border-brand-emerald/30 flex justify-between items-center animate-slideIn shadow-[0_0_15px_rgba(16,185,129,0.1)]';
    div.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-brand-emerald/20 text-brand-emerald flex items-center justify-center text-xs font-bold font-mono border border-brand-emerald/50">#${String(confirmedPeople.size).padStart(2, '0')}</div>
            <div>
                <div class="font-bold text-white capitalize tracking-wide font-mono">${name.replace(/_/g, ' ')}</div>
                <div class="text-[9px] text-brand-emerald uppercase tracking-widest">Clearance Granted</div>
            </div>
        </div>
        <span class="text-[10px] text-brand-emerald font-mono bg-brand-emerald/10 px-2 py-1 rounded border border-brand-emerald/20">${time}</span>
    `;
    confirmedList.insertBefore(div, confirmedList.firstChild);
}

setInterval(() => {
    const now = Date.now();
    let hasChanges = false;
    for (const name in currentlyVisible) {
        if (now - currentlyVisible[name] > VISIBILITY_TIMEOUT_MS) {
            delete currentlyVisible[name];
            hasChanges = true;
        }
    }
    if (hasChanges) renderPresenceList();
}, 1000);

function renderPresenceList() {
    const names = Object.keys(currentlyVisible);
    if (names.length === 0 || Object.keys(trackedFaces).length === 0) {
        attendanceList.innerHTML = '<div class="text-center text-slate-500/50 mt-10 text-sm font-mono tracking-widest animate-pulse">NO ENTITIES DETECTED</div>';
        return;
    }
    attendanceList.innerHTML = ''; 
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    
    names.forEach(name => {
        const div = document.createElement('div');
        div.className = 'bg-black/60 p-3 rounded-xl border border-brand-cyan/50 flex justify-between items-center animate-slideIn shadow-[0_0_15px_rgba(0,210,255,0.2)] backdrop-blur-sm';
        div.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="relative flex h-3 w-3 ml-2">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-cyan opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-3 w-3 bg-brand-cyan"></span>
                </div>
                <div>
                    <div class="font-bold text-white capitalize tracking-wide font-mono">${name.replace(/_/g, ' ')}</div>
                    <div class="text-[9px] text-brand-cyan uppercase tracking-widest">Active Presence</div>
                </div>
            </div>
        `;
        attendanceList.appendChild(div);
    });
}

async function populateCameraDevices() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        availableCameras = devices.filter(d => d.kind === 'videoinput');
        
        if (cameraSelect) {
            cameraSelect.innerHTML = '';
            if (availableCameras.length === 0) {
                cameraSelect.innerHTML = '<option value="">NO CAMERAS FOUND</option>';
                return;
            }

            availableCameras.forEach((cam, idx) => {
                const option = document.createElement('option');
                option.value = cam.deviceId;
                let label = cam.label || `Camera ${idx + 1}`;
                if (label.toLowerCase().includes('front') || label.toLowerCase().includes('user') || label.toLowerCase().includes('facing 0')) {
                    label = `🤳 Front Camera (${label.slice(0, 15)})`;
                } else if (label.toLowerCase().includes('back') || label.toLowerCase().includes('environment') || label.toLowerCase().includes('facing 1')) {
                    label = `📷 Back Camera (${label.slice(0, 15)})`;
                }
                option.textContent = label;
                cameraSelect.appendChild(option);
            });
        }
    } catch (err) {
        console.warn("Could not enumerate camera devices:", err);
    }
}

if (cameraSelect) {
    cameraSelect.addEventListener('change', (e) => {
        const deviceId = e.target.value;
        if (deviceId) {
            logToTerminal(`Switching camera input to ID: ${deviceId.slice(0, 8)}...`, 'info');
            startCamera(deviceId);
        }
    });
}

async function startCamera(selectedDeviceId = null) {
    try {
        if (currentStream) {
            currentStream.getTracks().forEach(track => track.stop());
        }

        const videoConstraints = selectedDeviceId 
            ? { deviceId: { exact: selectedDeviceId } }
            : { facingMode: "user" };

        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: videoConstraints 
        });
        
        currentStream = stream;
        video.srcObject = stream;

        // Detect if active camera is front/user facing
        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings ? track.getSettings() : {};
        const label = (track.label || "").toLowerCase();
        
        if (settings.facingMode === 'user' || label.includes('front') || label.includes('user')) {
            isFrontCamera = true;
            video.classList.add('mirror-video');
        } else if (settings.facingMode === 'environment' || label.includes('back') || label.includes('environment')) {
            isFrontCamera = false;
            video.classList.remove('mirror-video');
        } else {
            // Default behavior if undetermined
            isFrontCamera = !selectedDeviceId;
            if (isFrontCamera) video.classList.add('mirror-video');
            else video.classList.remove('mirror-video');
        }

        video.onloadedmetadata = () => {
            canvas.width = video.videoWidth; 
            canvas.height = video.videoHeight;
            overlayCanvas.width = video.videoWidth; 
            overlayCanvas.height = video.videoHeight;
            
            // Refresh device labels once permission is granted
            populateCameraDevices().then(() => {
                if (selectedDeviceId && cameraSelect) {
                    cameraSelect.value = selectedDeviceId;
                }
            });

            requestAnimationFrame(renderLoop);
        };
    } catch (err) {
        showToast("Camera access failed or unavailable", "error");
        logToTerminal("ERROR: Camera hardware unavailable.", "error");
    }
}

// --- CORE RENDER LOOP ---
function renderLoop() {
    frameCount++;
    if (Date.now() - lastFpsTime >= 1000) {
        document.getElementById('fps-counter').textContent = frameCount;
        frameCount = 0;
        lastFpsTime = Date.now();
    }

    if (ws && ws.readyState === WebSocket.OPEN && !isProcessing) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        if (isRegistering) {
            isProcessing = true;
            ws.send(JSON.stringify({ type: 'register_frame', image: canvas.toDataURL('image/jpeg', 0.8) }));
        } else {
            isProcessing = true;
            ws.send(JSON.stringify({ type: 'frame', image: canvas.toDataURL('image/jpeg', 0.7) }));
        }
    }

    if (isRegistering) drawGamifiedScanner();
    else drawSmoothFaces();

    requestAnimationFrame(renderLoop);
}

document.getElementById('delete-all-btn').addEventListener('click', async () => {
    if (!confirm('⚠️ WARNING: This wipes the entire AWS biometric database. Are you sure?')) return;
    
    logToTerminal('Wipe command initiated...', 'warning');
    try {
        const response = await fetch('/delete_faces', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            logToTerminal('AWS Collection wiped.', 'success');
            showToast("Database Wiped Clean", "success");
            confirmedPeople.clear();
            confirmedList.innerHTML = '<div class="text-center text-slate-500/50 mt-10 text-sm font-mono tracking-widest">AWAITING CONFIRMATION</div>';
        } else {
            logToTerminal(data.message, 'error');
            showToast(data.message, "error");
        }
    } catch (err) {
        logToTerminal(err.message, 'error');
        showToast("Network Error", "error");
    }
});

document.getElementById('download-btn').addEventListener('click', () => {
    showToast("Generating Security Log...", "info");
    logToTerminal("Exporting security clearance logs...", "info");
    
    // Trigger native download
    const a = document.createElement('a');
    a.href = '/logs';
    a.download = ''; // Browser will use filename from Content-Disposition header
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    setTimeout(() => {
        showToast("Download Complete", "success");
        logToTerminal("Security logs exported successfully.", "success");
    }, 1500);
});

connectWebSocket();
startCamera();
