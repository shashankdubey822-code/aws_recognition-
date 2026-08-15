const video = document.getElementById('videoElement');
const canvas = document.getElementById('canvasElement');
const ctx = canvas.getContext('2d', { willReadFrequently: true });
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const attendanceList = document.getElementById('attendance-list');
const confirmedList = document.getElementById('confirmed-list');
const terminalLogs = document.getElementById('terminal-logs');
const debugCrops = document.getElementById('debug-crops');
const cropCount = document.getElementById('crop-count');
const cameraSelect = document.getElementById('camera-select');

// --- REGISTRATION UI ELEMENTS ---
const addStudentBtn = document.getElementById('add-student-btn');
const modalBackdrop = document.getElementById('modal-backdrop');
const cancelBtn = document.getElementById('cancel-btn');
const startScanBtn = document.getElementById('start-scan-btn');
const studentNameInput = document.getElementById('student-name-input');
const studentRollInput = document.getElementById('student-roll-input');
const regOverlay = document.getElementById('reg-overlay');
const regInstruction = document.getElementById('reg-instruction');
const regSubtext = document.getElementById('reg-subtext');
const regProgressBar = document.getElementById('reg-progress-bar');

// --- SESSION MANAGEMENT UI ELEMENTS ---
const startSessionBtn = document.getElementById('start-session-btn');
const stopSessionBtn = document.getElementById('stop-session-btn');
const sessionDurationSelect = document.getElementById('session-duration-select');
const sessionTimerBox = document.getElementById('session-timer-box');
const sessionTimerDisplay = document.getElementById('session-timer-display');
const sessionStatusLabel = document.getElementById('session-status-label');
const sessionIndicator = document.getElementById('session-indicator');
const sessionPresentCount = document.getElementById('session-present-count');

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
let sessionPresentSet = new Set();
const VISIBILITY_TIMEOUT_MS = 3000;

// --- SESSION COUNTDOWN STATE ---
let sessionTimerInterval = null;
let sessionRemainingSeconds = 0;

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
    if (!container) return;
    
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
            <h4 class="text-xs font-bold capitalize text-white font-mono">${type.toUpperCase()}</h4>
            <p class="text-xs text-slate-300 font-sans">${message}</p>
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
    if (!terminalLogs) return;
    const div = document.createElement('div');
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    
    let colorClass = 'text-slate-300';
    let prefix = '[-]';
    if (type === 'error' || msg.includes('ERROR')) { colorClass = 'text-red-400 font-bold'; prefix = '[!]'; }
    else if (type === 'warning' || msg.includes('WARNING')) { colorClass = 'text-amber-300 font-bold'; prefix = '[?]'; }
    else if (type === 'success' || msg.includes('Granted')) { colorClass = 'text-emerald-400 font-bold'; prefix = '[+]'; }
    
    div.className = `${colorClass} flex items-start gap-2 break-all`;
    div.innerHTML = `<span class="text-slate-500 select-none">[${time}]</span> <span class="font-bold select-none">${prefix}</span> <span>${msg}</span>`;
    
    terminalLogs.appendChild(div);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
    
    while (terminalLogs.children.length > 50) {
        terminalLogs.removeChild(terminalLogs.firstChild);
    }
}

// Calculate dynamic WebSocket URL
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;

// --- REGISTRATION HANDLERS ---
if (addStudentBtn) {
    addStudentBtn.addEventListener('click', () => {
        modalBackdrop.classList.remove('hidden');
        studentNameInput.value = '';
        studentRollInput.value = '';
        studentNameInput.focus();
    });
}

if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
        modalBackdrop.classList.add('hidden');
    });
}

if (startScanBtn) {
    startScanBtn.addEventListener('click', () => {
        const name = studentNameInput.value.trim();
        const roll = studentRollInput.value.trim();
        
        if (!name) { 
            showToast("Please enter Student Full Name", "error"); 
            studentNameInput.focus();
            return; 
        }
        if (!roll) { 
            showToast("Please enter Student Roll Number / ID", "error"); 
            studentRollInput.focus();
            return; 
        }
        
        isRegistering = true;
        regProgress = 0;
        targetX = overlayCanvas.width / 2;
        targetY = overlayCanvas.height / 2;
        currentDotX = targetX;
        currentDotY = targetY;

        modalBackdrop.classList.add('hidden');
        regOverlay.classList.remove('hidden');
        if (regProgressBar) regProgressBar.style.width = '0%';
        
        regInstruction.textContent = "INITIALIZING 3D SCAN";
        regSubtext.textContent = "Align face within target vector...";
        
        trackedFaces = {};
        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        
        ws.send(JSON.stringify({ 
            type: 'start_registration', 
            name: name,
            roll_number: roll
        }));
        logToTerminal(`Initiated biometric mapping for ${name} (Roll: ${roll})`, 'info');
    });
}

// --- SESSION MANAGEMENT LOGIC ---
function formatTimerDisplay(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function startCountdown(durationSeconds) {
    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
    sessionRemainingSeconds = durationSeconds;
    
    sessionTimerBox.classList.remove('hidden');
    startSessionBtn.classList.add('hidden');
    stopSessionBtn.classList.remove('hidden');
    
    sessionStatusLabel.textContent = "MONITORING ACTIVE";
    sessionIndicator.className = "inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping";
    
    sessionTimerDisplay.textContent = formatTimerDisplay(sessionRemainingSeconds);
    
    sessionTimerInterval = setInterval(() => {
        sessionRemainingSeconds--;
        if (sessionRemainingSeconds <= 0) {
            clearInterval(sessionTimerInterval);
            sessionTimerDisplay.textContent = "00:00";
            sessionStatusLabel.textContent = "COMPLETING...";
            return;
        }
        sessionTimerDisplay.textContent = formatTimerDisplay(sessionRemainingSeconds);
    }, 1000);
}

function resetSessionUI() {
    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
    sessionTimerInterval = null;
    
    sessionTimerBox.classList.add('hidden');
    stopSessionBtn.classList.add('hidden');
    startSessionBtn.classList.remove('hidden');
    
    sessionStatusLabel.textContent = "STANDBY / CONCLUDED";
    sessionIndicator.className = "inline-block w-2 h-2 rounded-full bg-slate-500";
}

if (startSessionBtn) {
    startSessionBtn.addEventListener('click', () => {
        const duration = parseInt(sessionDurationSelect.value) || 50;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'start_session',
                duration_minutes: duration
            }));
            logToTerminal(`[SESSION] Triggered start command (${duration} mins)...`, 'info');
        } else {
            showToast("Server connection offline", "error");
        }
    });
}

if (stopSessionBtn) {
    stopSessionBtn.addEventListener('click', () => {
        if (!confirm("Are you sure you want to STOP monitoring? This will immediately compile the Excel sheet and email it to the teacher.")) return;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'stop_session' }));
            logToTerminal(`[SESSION] Manual stop triggered. Dispatching report...`, 'warning');
        }
    });
}

// --- AUDIO ENGINE ---
let audioCtx;
function initAudio() { if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
function playTone(freq, type, duration, vol=0.1) {
    if (!audioCtx) return;
    try {
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
    } catch(e){}
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
    hideChallengeOverlay(faceId);
    
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
    `;
    
    const deadline = Date.now() + 15000;
    activeChallenges[faceId] = { instruction, deadline, element: panel };

    const arrow = DIRECTION_ARROWS[instruction] || instruction;
    panel.innerHTML = `
        <div style="font-size: 5rem; color: #ef4444; line-height: 1; text-shadow: 0 0 30px rgba(239,68,68,0.8);">${arrow}</div>
        <div style="font-family: Orbitron, monospace; font-size: 1.5rem; font-weight: 900; color: white; letter-spacing: 0.2em; text-transform: uppercase; margin-top: 0.5rem; text-shadow: 0 0 15px rgba(255,255,255,0.8);">
            TURN HEAD ${instruction}
        </div>
        <div style="font-family: Inter, sans-serif; font-size: 0.85rem; color: #fca5a5; margin-top: 0.5rem; letter-spacing: 0.1em;">
            LIVENESS VERIFICATION IN PROGRESS
        </div>
        <div style="margin-top: 1rem; width: 200px; height: 6px; background: rgba(0,0,0,0.5); border-radius: 3px; overflow: hidden; border: 1px solid rgba(239,68,68,0.5);">
            <div id="challenge-timer-${faceId}" style="height: 100%; width: 100%; background: #ef4444; transition: width 0.1s linear;"></div>
        </div>
    `;

    container.appendChild(panel);
}

function updateChallengeOverlay(faceId, outcome) {
    const challenge = activeChallenges[faceId];
    if (!challenge || !challenge.element) return;
    
    const panel = challenge.element;
    if (outcome === 'passed') {
        panel.style.background = 'rgba(16, 185, 129, 0.2)';
        panel.style.borderColor = 'rgba(16, 185, 129, 0.9)';
        panel.innerHTML = `
            <div style="font-size: 4rem; color: #10b981;">✓</div>
            <div style="font-family: Orbitron, monospace; font-size: 1.3rem; font-weight: 900; color: #10b981; letter-spacing: 0.15em;">
                LIVENESS CONFIRMED
            </div>
        `;
    } else if (outcome === 'failed') {
        panel.style.background = 'rgba(239, 68, 68, 0.4)';
        panel.style.borderColor = '#ef4444';
        panel.innerHTML = `
            <div style="font-size: 4rem; color: #ef4444;">✗</div>
            <div style="font-family: Orbitron, monospace; font-size: 1.3rem; font-weight: 900; color: #ef4444; letter-spacing: 0.15em;">
                SPOOF DETECTED — ACCESS DENIED
            </div>
        `;
    }
}

function hideChallengeOverlay(faceId) {
    const existing = document.getElementById(`challenge-overlay-${faceId}`);
    if (existing) existing.remove();
    delete activeChallenges[faceId];
}

// --- TARGET TRACKING CANVAS DRAWER ---
function updateTargetFaces(faces) {
    const now = Date.now();
    faces.forEach(f => {
        if (!trackedFaces[f.id]) {
            trackedFaces[f.id] = {
                id: f.id,
                name: f.name,
                roll_number: f.roll_number || 'N/A',
                status: f.status,
                score: f.score,
                currBox: { ...f.box },
                targetBox: { ...f.box },
                lastSeen: now
            };
        } else {
            trackedFaces[f.id].name = f.name;
            trackedFaces[f.id].roll_number = f.roll_number || 'N/A';
            trackedFaces[f.id].status = f.status;
            trackedFaces[f.id].score = f.score;
            trackedFaces[f.id].targetBox = { ...f.box };
            trackedFaces[f.id].lastSeen = now;
        }
    });

    for (const id in trackedFaces) {
        if (now - trackedFaces[id].lastSeen > BOX_FADEOUT_MS) {
            delete trackedFaces[id];
        }
    }
}

function drawHighTechCorners(x, y, w, h, color, size = 15) {
    overlayCtx.strokeStyle = color;
    overlayCtx.lineWidth = 2.5;
    overlayCtx.beginPath();
    // Top-Left
    overlayCtx.moveTo(x, y + size); overlayCtx.lineTo(x, y); overlayCtx.lineTo(x + size, y);
    // Top-Right
    overlayCtx.moveTo(x + w - size, y); overlayCtx.lineTo(x + w, y); overlayCtx.lineTo(x + w, y + size);
    // Bottom-Left
    overlayCtx.moveTo(x, y + h - size); overlayCtx.lineTo(x, y + h); overlayCtx.lineTo(x + size, y + h);
    // Bottom-Right
    overlayCtx.moveTo(x + w - size, y + h); overlayCtx.lineTo(x + w, y + h); overlayCtx.lineTo(x + w, y + h - size);
    overlayCtx.stroke();
}

function drawSmoothFaces() {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    const now = Date.now();

    for (const id in trackedFaces) {
        const obj = trackedFaces[id];
        
        // Lerp coordinates
        obj.currBox.x += (obj.targetBox.x - obj.currBox.x) * LERP_FACTOR;
        obj.currBox.y += (obj.targetBox.y - obj.currBox.y) * LERP_FACTOR;
        obj.currBox.w += (obj.targetBox.w - obj.currBox.w) * LERP_FACTOR;
        obj.currBox.h += (obj.targetBox.h - obj.currBox.h) * LERP_FACTOR;

        const { x, y, w, h } = obj.currBox;
        
        let color = '#00d2ff'; // Cyan default
        let label = obj.name;
        if (obj.status === 'match') {
            color = '#10b981'; // Emerald
        } else if (obj.status === 'spoof' || obj.name.includes('SPOOF')) {
            color = '#ef4444'; // Red
        } else if (obj.status === 'failed') {
            color = '#f59e0b'; // Amber
        }

        // Draw Bounding Box Corners
        drawHighTechCorners(x, y, w, h, color);

        // Name Header Tag
        overlayCtx.fillStyle = 'rgba(0, 0, 0, 0.75)';
        overlayCtx.fillRect(x, Math.max(0, y - 28), Math.max(120, w), 24);
        
        overlayCtx.fillStyle = color;
        overlayCtx.font = 'bold 12px Orbitron, monospace';
        overlayCtx.fillText(label, x + 6, Math.max(16, y - 12));
    }
}

function drawGamifiedScanner() {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    const cx = overlayCanvas.width / 2;
    const cy = overlayCanvas.height / 2;
    const r = Math.min(cx, cy) * 0.6;

    regPulseAngle += 0.05;
    
    // Reticle Circles
    overlayCtx.strokeStyle = 'rgba(0, 210, 255, 0.4)';
    overlayCtx.lineWidth = 2;
    overlayCtx.beginPath();
    overlayCtx.arc(cx, cy, r, 0, Math.PI * 2);
    overlayCtx.stroke();

    overlayCtx.strokeStyle = '#00d2ff';
    overlayCtx.lineWidth = 4;
    overlayCtx.beginPath();
    overlayCtx.arc(cx, cy, r, -Math.PI / 2, (-Math.PI / 2) + ((regProgress / 100) * Math.PI * 2));
    overlayCtx.stroke();

    // Crosshair target
    overlayCtx.strokeStyle = 'rgba(16, 185, 129, 0.7)';
    overlayCtx.beginPath();
    overlayCtx.moveTo(cx - 20, cy); overlayCtx.lineTo(cx + 20, cy);
    overlayCtx.moveTo(cx, cy - 20); overlayCtx.lineTo(cx, cy + 20);
    overlayCtx.stroke();
}

function updateDebugCrops(faces) {
    if (!debugCrops) return;
    debugCrops.innerHTML = '';
    if (cropCount) cropCount.textContent = faces.length;

    if (faces.length === 0) {
        debugCrops.innerHTML = '<div class="text-xs text-slate-600 italic font-mono">Awaiting target...</div>';
        return;
    }

    faces.forEach(face => {
        if (face.crop) {
            const container = document.createElement('div');
            container.className = 'relative w-14 h-14 rounded-lg overflow-hidden border border-white/20 bg-black';
            const img = document.createElement('img');
            img.src = face.crop;
            img.className = 'w-full h-full object-cover';
            
            const badge = document.createElement('div');
            badge.className = 'absolute bottom-0 left-0 right-0 bg-black/80 text-[7px] text-center py-0.5 truncate text-white font-mono';
            badge.textContent = face.status === 'match' ? 'VERIFIED' : (face.status === 'spoof' ? 'SPOOF' : 'SCAN');
            
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
        const statusElem = document.getElementById('ws-status');
        if (statusElem) {
            statusElem.textContent = 'SYSTEM ONLINE';
            statusElem.className = 'text-xs font-mono text-emerald-400 tracking-wide';
        }
        logToTerminal("WebSocket Connected. Security Core active.", "success");
        showToast("Connected to Security Subsystem", "success");
        
        // Request active session status
        ws.send(JSON.stringify({ type: 'get_session_status' }));
        
        pingInterval = setInterval(() => { 
            if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'heartbeat' })); 
        }, 10000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'error') {
            isProcessing = false;
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
            return;
        }

        // --- SESSION MESSAGE HANDLERS ---
        if (data.type === 'session_started') {
            startCountdown(data.duration_minutes * 60);
            
            // Clean slate for the new session (starts from 0 students)
            confirmedPeople.clear();
            if (confirmedList) confirmedList.innerHTML = '<div class="text-center text-slate-500/50 mt-10 text-sm font-mono tracking-widest">AWAITING VERIFICATION</div>';
            if (sessionPresentCount) sessionPresentCount.textContent = '0';
            for (const k in currentlyVisible) delete currentlyVisible[k];
            renderPresenceList();

            showToast(`New session started (${data.duration_minutes}m) — Records reset to 0`, "success");
            logToTerminal(`[SESSION] ▶️ Fresh Session Active: ${data.session_id} (${data.duration_minutes} mins, 0 attendees)`, "success");
            initAudio();
            playTone(880, 'sine', 0.2);
            return;
        }

        if (data.type === 'session_stopped') {
            resetSessionUI();
            showToast(`Session concluded! Report emailed to teacher. (${data.total_attendees} students)`, "success");
            logToTerminal(`[SESSION] 🏁 Session ended. Attendees: ${data.total_attendees}. Excel sent via email.`, "success");
            initAudio();
            playTone(1200, 'triangle', 0.5);
            return;
        }

        if (data.type === 'session_status') {
            if (data.active && data.remaining_seconds > 0) {
                startCountdown(data.remaining_seconds);
                logToTerminal(`[SESSION] Resumed active monitoring session (${Math.ceil(data.remaining_seconds/60)} mins remaining)`, "info");
            } else {
                resetSessionUI();
            }
            return;
        }

        // --- INTRUDER ALERT ---
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

        // --- REGISTRATION MESSAGES ---
        if (data.type === 'registration_status') {
            isProcessing = false;
            if (data.progress > regProgress) {
                initAudio();
                playTone(1000, 'sine', 0.1);
            }
            regProgress = data.progress;
            if (regProgressBar) regProgressBar.style.width = `${regProgress}%`;
            regSubtext.textContent = `${data.message}`;

            if (regProgress >= 100 && isRegistering) {
                isRegistering = false;
                regInstruction.textContent = "Processing Identity...";
                logToTerminal("Persisting Biometric Vector to Cloud...", "info");
            }
            return;
        } 
        
        if (data.type === 'registration_waiting') {
            isProcessing = false;
            regSubtext.textContent = data.message;
            return;
        } 
        
        if (data.type === 'registration_success') {
            playTone(1200, 'triangle', 0.4, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "success");
            showToast("Student Registered Successfully", "success");
            return;
        } 
        
        if (data.type === 'registration_error') {
            playTone(200, 'sawtooth', 0.5, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
            return;
        }

        // --- ATTENDANCE VERIFIED ---
        if (data.type === 'attendance') {
            const displayName = data.name;
            const rollNumber = data.roll_number || 'N/A';
            const uniqueKey = `${rollNumber}_${displayName}`;

            currentlyVisible[uniqueKey] = { name: displayName, roll: rollNumber, ts: Date.now() };
            
            for (const fid in activeChallenges) {
                hideChallengeOverlay(fid);
            }
            
            renderPresenceList();
            addConfirmedEntry(displayName, rollNumber, data.time);
            showToast(`Clearance Granted: ${displayName} (${rollNumber})`, "success");
            playTone(1500, 'sine', 0.1);
            logToTerminal(`Clearance Granted: ${displayName} [Roll: ${rollNumber}]`, "success");
            return;
        }

        // --- CHALLENGES ---
        if (data.type === 'challenge') {
            const fid = data.face_id;
            const instruction = data.instruction;
            showChallengeOverlay(fid, instruction);
            initAudio();
            playTone(440, 'sine', 0.3, 0.15);
            speakWarning(`Security check. Turn your head ${instruction}.`);
            logToTerminal(`[CHALLENGE] Face ${fid}: Turn ${instruction}`, 'warning');
            return;
        }

        if (data.type === 'challenge_passed') {
            const fid = data.face_id;
            updateChallengeOverlay(fid, 'passed');
            playTone(1200, 'triangle', 0.4, 0.2);
            setTimeout(() => hideChallengeOverlay(fid), 2000);
            logToTerminal(`[CHALLENGE] ✅ Face ${fid} verified as real!`, 'success');
            return;
        }

        if (data.type === 'challenge_failed') {
            const fid = data.face_id;
            updateChallengeOverlay(fid, 'failed');
            playTone(200, 'sawtooth', 0.8, 0.3);
            speakWarning("Spoof detected. Access denied.");
            setTimeout(() => hideChallengeOverlay(fid), 3000);
            logToTerminal(`[CHALLENGE] ❌ Face ${fid} SPOOF CONFIRMED`, 'error');
            return;
        } 
        
        // --- READY / FRAME RESULTS ---
        if (data.type === 'ready') {
            isProcessing = false;
            if (data.faces && data.faces.length > 0) {
                updateTargetFaces(data.faces);
                if (!isRegistering) updateDebugCrops(data.faces);
                
                data.faces.forEach(face => {
                    if (face.status === 'match') {
                        const roll = face.roll_number || 'N/A';
                        const key = `${roll}_${face.raw_name || face.name}`;
                        currentlyVisible[key] = { name: face.raw_name || face.name, roll: roll, ts: Date.now() };
                    }
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
        const statusElem = document.getElementById('ws-status');
        if (statusElem) {
            statusElem.textContent = 'RECONNECTING...';
            statusElem.className = 'text-xs font-mono text-red-500 tracking-wide animate-pulse';
        }
        showToast("Lost connection to Security Subsystem", "error");
        
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        setTimeout(connectWebSocket, timeout);
        reconnectAttempts++;
    };
}

function addConfirmedEntry(name, rollNumber, time) {
    const key = `${rollNumber}_${name}`;
    if (confirmedPeople.has(key)) return;
    if (confirmedPeople.size === 0) confirmedList.innerHTML = '';
    confirmedPeople.add(key);
    
    // Update session present counter
    if (sessionPresentCount) sessionPresentCount.textContent = confirmedPeople.size;
    
    const div = document.createElement('div');
    div.className = 'bg-brand-emerald/10 p-3 rounded-xl border border-brand-emerald/30 flex justify-between items-center animate-slideIn shadow-[0_0_15px_rgba(16,185,129,0.1)]';
    div.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-brand-emerald/20 text-brand-emerald flex items-center justify-center text-xs font-bold font-mono border border-brand-emerald/50">#${String(confirmedPeople.size).padStart(2, '0')}</div>
            <div>
                <div class="font-bold text-white tracking-wide font-mono text-xs">${name}</div>
                <div class="text-[9px] text-brand-cyan font-mono uppercase tracking-wider">Roll: ${rollNumber}</div>
            </div>
        </div>
        <span class="text-[10px] text-brand-emerald font-mono bg-brand-emerald/10 px-2 py-1 rounded border border-brand-emerald/20">${time}</span>
    `;
    confirmedList.insertBefore(div, confirmedList.firstChild);
}

setInterval(() => {
    const now = Date.now();
    let hasChanges = false;
    for (const key in currentlyVisible) {
        if (now - currentlyVisible[key].ts > VISIBILITY_TIMEOUT_MS) {
            delete currentlyVisible[key];
            hasChanges = true;
        }
    }
    if (hasChanges) renderPresenceList();
}, 1000);

function renderPresenceList() {
    const keys = Object.keys(currentlyVisible);
    if (keys.length === 0 || Object.keys(trackedFaces).length === 0) {
        attendanceList.innerHTML = '<div class="text-center text-slate-500/50 mt-10 text-sm font-mono tracking-widest animate-pulse">NO ENTITIES DETECTED</div>';
        return;
    }
    attendanceList.innerHTML = ''; 
    
    keys.forEach(key => {
        const item = currentlyVisible[key];
        const div = document.createElement('div');
        div.className = 'bg-black/60 p-3 rounded-xl border border-brand-cyan/50 flex justify-between items-center animate-slideIn shadow-[0_0_15px_rgba(0,210,255,0.2)] backdrop-blur-sm';
        div.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="relative flex h-3 w-3 ml-1">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-cyan opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-3 w-3 bg-brand-cyan"></span>
                </div>
                <div>
                    <div class="font-bold text-white tracking-wide font-mono text-xs">${item.name}</div>
                    <div class="text-[9px] text-brand-cyan font-mono uppercase tracking-wider">Roll: ${item.roll}</div>
                </div>
            </div>
            <span class="text-[9px] text-brand-cyan uppercase font-mono px-2 py-0.5 rounded bg-brand-cyan/10 border border-brand-cyan/30">Active</span>
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
                if (label.toLowerCase().includes('front') || label.toLowerCase().includes('user')) {
                    label = `🤳 Front Camera (${label.slice(0, 15)})`;
                } else if (label.toLowerCase().includes('back') || label.toLowerCase().includes('environment')) {
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
            logToTerminal(`Switching camera input...`, 'info');
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

        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings ? track.getSettings() : {};
        const label = (track.label || "").toLowerCase();
        
        if (settings.facingMode === 'user' || label.includes('front') || label.includes('user')) {
            isFrontCamera = true;
            video.classList.add('mirror-video');
        } else {
            isFrontCamera = false;
            video.classList.remove('mirror-video');
        }

        video.onloadedmetadata = () => {
            canvas.width = video.videoWidth; 
            canvas.height = video.videoHeight;
            overlayCanvas.width = video.videoWidth; 
            overlayCanvas.height = video.videoHeight;
            
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
        const fpsElem = document.getElementById('fps-counter');
        if (fpsElem) fpsElem.textContent = frameCount;
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

const deleteAllBtn = document.getElementById('delete-all-btn');
if (deleteAllBtn) {
    deleteAllBtn.addEventListener('click', async () => {
        if (!confirm('⚠️ WARNING: This wipes the entire AWS biometric database and local records. Are you sure?')) return;
        
        logToTerminal('Wipe command initiated...', 'warning');
        try {
            const response = await fetch('/delete_faces', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                logToTerminal('AWS Collection & Local logs wiped.', 'success');
                showToast("Database Wiped Clean", "success");
                confirmedPeople.clear();
                if (sessionPresentCount) sessionPresentCount.textContent = '0';
                confirmedList.innerHTML = '<div class="text-center text-slate-500/50 mt-10 text-sm font-mono tracking-widest">AWAITING VERIFICATION</div>';
            } else {
                logToTerminal(data.message, 'error');
                showToast(data.message, "error");
            }
        } catch (err) {
            logToTerminal(err.message, 'error');
            showToast("Network Error", "error");
        }
    });
}

const downloadBtn = document.getElementById('download-btn');
if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
        showToast("Generating Master Security Log...", "info");
        logToTerminal("Exporting master security logs...", "info");
        
        const a = document.createElement('a');
        a.href = '/logs';
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        setTimeout(() => {
            showToast("Master Log Download Complete", "success");
            logToTerminal("Master security logs exported successfully.", "success");
        }, 1500);
    });
}

connectWebSocket();
startCamera();
