const video = document.getElementById('videoElement');
const canvas = document.getElementById('canvasElement');
const ctx = canvas.getContext('2d');
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const statusBadge = document.getElementById('status-badge');
const attendanceList = document.getElementById('attendance-list');
const confirmedList = document.getElementById('confirmed-list');
const terminalLogs = document.getElementById('terminal-logs');
const debugCrops = document.getElementById('debug-crops');
const cropCount = document.getElementById('crop-count');

// --- NEW REGISTRATION UI ELEMENTS ---
const addStudentBtn = document.getElementById('add-student-btn');
const modalBackdrop = document.getElementById('modal-backdrop');
const cancelBtn = document.getElementById('cancel-btn');
const startScanBtn = document.getElementById('start-scan-btn');
const studentNameInput = document.getElementById('student-name-input');
const regOverlay = document.getElementById('reg-overlay');
const regInstruction = document.getElementById('reg-instruction');
const regSubtext = document.getElementById('reg-subtext');

let ws;
let isProcessing = false;
let frameCount = 0;
let lastFpsTime = Date.now();
let reconnectAttempts = 0;
let pingInterval;

let currentlyVisible = {};
let confirmedPeople = new Set(); 
const VISIBILITY_TIMEOUT_MS = 8000;

// --- ADVANCED GAMIFIED REGISTRATION STATE ---
let isRegistering = false;
const REQUIRED_REG_FRAMES = 12; // 4 center, 4 left, 4 right
let regProgress = 0;
let regPulseAngle = 0;
let flashAlpha = 0; // For visual capture feedback

// Animation state for the glowing dot
let targetX = 0;
let targetY = 0;
let currentDotX = 0;
let currentDotY = 0;

// 🔧 FIX #1: Keep face visible longer even if AWS misses it
// Increase fadeout to prevent premature disappearance
const BOX_FADEOUT_MS = 3000; // Was 1000ms - TOO SHORT! Now 3 seconds
const EXTENDED_VISIBILITY_MS = 15000; // Extended from 8000ms

// --- SCI-FI AUDIO ENGINE (No external files needed) ---
let audioCtx;
function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
}
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

// --- ADVANCED SMOOTH TRACKING STATE ---
let trackedFaces = {}; 
const LERP_FACTOR = 0.3; 
// NOTE: BOX_FADEOUT_MS is already defined above as 3000ms - do NOT redefine!

// Calculate dynamic WebSocket URL for Hugging Face Spaces
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;

// --- REGISTRATION EVENT HANDLERS ---
addStudentBtn.addEventListener('click', () => {
    modalBackdrop.classList.remove('hidden');
    studentNameInput.value = '';
    studentNameInput.focus();
});

cancelBtn.addEventListener('click', () => {
    modalBackdrop.classList.add('hidden');
});

startScanBtn.addEventListener('click', () => {
    // Replace spaces and special characters with underscores for AWS compatibility
    const name = studentNameInput.value.trim().replace(/ /g, '_').replace(/[^a-zA-Z0-9_.\-:]/g, '_');
    if (!name) {
        alert("Please enter a valid name.");
        return;
    }
    
    isRegistering = true;
    regProgress = 0;
    
    // Set initial dot position to center
    targetX = overlayCanvas.width / 2;
    targetY = overlayCanvas.height / 2;
    currentDotX = targetX;
    currentDotY = targetY;

    modalBackdrop.classList.add('hidden');
    regOverlay.classList.remove('hidden');
    
    // Hide the static CSS circle we had before, we will draw on canvas now
    regOverlay.querySelector('.border-dashed').classList.add('hidden');
    
    regInstruction.textContent = "Look at the Dot";
    regSubtext.textContent = "Initializing Scanner...";
    
    trackedFaces = {};
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    ws.send(JSON.stringify({ type: 'start_registration', name: name }));
});

function logToTerminal(msg) {
    const div = document.createElement('div');
    const time = new Date().toISOString().split('T')[1].slice(0, 12);
    div.innerHTML = `<span class="text-slate-500">[${time}]</span> <span class="${msg.includes('ERROR') ? 'text-red-400' : 'text-slate-300'}">${msg}</span>`;
    terminalLogs.appendChild(div);
    if (terminalLogs.children.length > 20) terminalLogs.removeChild(terminalLogs.firstChild);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
}

function updateTargetFaces(faces) {
    const now = Date.now();
    if (!faces) return;

    faces.forEach((face, index) => {
        if (!face.box) return;
        
        const id = face.name === 'Unknown' ? `unknown_${index}` : face.name;
        
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
        }
    });
}

function drawHighTechCorners(ctx, x, y, w, h, color, alpha) {
    const len = Math.min(w, h) * 0.15; 
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    ctx.beginPath();
    ctx.moveTo(x, y + len); ctx.lineTo(x, y); ctx.lineTo(x + len, y);
    ctx.moveTo(x + w - len, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + len);
    ctx.moveTo(x + w, y + h - len); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w - len, y + h);
    ctx.moveTo(x + len, y + h); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h - len);
    ctx.stroke();
    
    ctx.globalAlpha = alpha * 0.15;
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
    
    ctx.globalAlpha = alpha * 0.3;
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);
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
        const mirroredX = overlayCanvas.width - x - w;
        
        let color = '#ef4444'; 
        if (face.status === 'match') color = '#10b981'; 
        else if (face.status === 'verifying') color = '#3b82f6'; 
        else if (face.status === 'fail' && face.name !== 'Unknown') color = '#f59e0b'; 
        
        const alpha = age > 200 ? Math.max(0, 1 - ((age - 200) / 800)) : 1;
        
        drawHighTechCorners(overlayCtx, mirroredX, y, w, h, color, alpha);
        
        overlayCtx.globalAlpha = alpha;
        const labelText = `${face.name} ${face.score > 0 ? '(' + face.score + '%)' : ''}`;
        overlayCtx.font = 'bold 14px "Courier New", monospace';
        const textWidth = overlayCtx.measureText(labelText).width;
        
        overlayCtx.fillStyle = '#000000AA';
        overlayCtx.fillRect(mirroredX, y > 30 ? y - 25 : y + h + 5, textWidth + 10, 20);
        
        overlayCtx.fillStyle = color;
        overlayCtx.fillText(labelText, mirroredX + 5, y > 30 ? y - 10 : y + h + 19);
        
        overlayCtx.globalAlpha = 1.0;
    }
}

// --- GAMIFIED UI DRAWING ---
function drawGamifiedScanner() {
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    // Visual Flash Feedback
    if (flashAlpha > 0) {
        overlayCtx.fillStyle = `rgba(16, 185, 129, ${flashAlpha})`; // Emerald green flash
        overlayCtx.fillRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        flashAlpha -= 0.05; // Fade out quickly
    }
    
    // Smoothly animate the dot to its target destination
    currentDotX += (targetX - currentDotX) * 0.1;
    currentDotY += (targetY - currentDotY) * 0.1;

    // Base glowing circle
    regPulseAngle += 0.1;
    const pulseRadius = 30 + Math.sin(regPulseAngle) * 5;
    
    overlayCtx.beginPath();
    overlayCtx.arc(currentDotX, currentDotY, pulseRadius, 0, Math.PI * 2);
    overlayCtx.fillStyle = 'rgba(59, 130, 246, 0.4)'; // Blue pulse
    overlayCtx.fill();

    // Solid inner dot
    overlayCtx.beginPath();
    overlayCtx.arc(currentDotX, currentDotY, 10, 0, Math.PI * 2);
    overlayCtx.fillStyle = '#3b82f6';
    overlayCtx.fill();

    // Progress Arc Ring
    const progressPct = regProgress / REQUIRED_REG_FRAMES;
    if (progressPct > 0) {
        overlayCtx.beginPath();
        overlayCtx.arc(currentDotX, currentDotY, 45, -Math.PI / 2, (-Math.PI / 2) + (Math.PI * 2 * progressPct));
        overlayCtx.strokeStyle = '#10b981'; // Emerald progress
        overlayCtx.lineWidth = 6;
        overlayCtx.lineCap = 'round';
        overlayCtx.stroke();
    }
    
    // Draw tracking corners around face if available
    for (const id in trackedFaces) {
        const face = trackedFaces[id];
        if (Date.now() - face.lastUpdate > BOX_FADEOUT_MS) continue;
        
        // Update interpolation
        face.currentBox.x += (face.targetBox.x - face.currentBox.x) * LERP_FACTOR;
        face.currentBox.y += (face.targetBox.y - face.currentBox.y) * LERP_FACTOR;
        face.currentBox.w += (face.targetBox.w - face.currentBox.w) * LERP_FACTOR;
        face.currentBox.h += (face.targetBox.h - face.currentBox.h) * LERP_FACTOR;
        
        const { x, y, w, h } = face.currentBox;
        const mirroredX = overlayCanvas.width - x - w;
        
        // Draw a minimalist scanning bracket
        drawHighTechCorners(overlayCtx, mirroredX, y, w, h, '#3b82f6', 0.5);
    }
}

function updateDebugCrops(faces) {
    debugCrops.innerHTML = '';
    if (!faces || faces.length === 0) {
        debugCrops.innerHTML = '<div class="text-xs text-slate-600 italic">Waiting for detection...</div>';
        cropCount.textContent = '0 faces';
        return;
    }
    cropCount.textContent = `${faces.length} faces`;

    faces.forEach(face => {
        if (face.crop) {
            const container = document.createElement('div');
            container.className = 'relative flex-shrink-0';
            const img = document.createElement('img');
            img.src = face.crop;
            let borderCol = 'border-slate-700';
            if (face.status === 'match') borderCol = 'border-emerald-500';
            else if (face.status === 'verifying') borderCol = 'border-blue-500';
            else if (face.status === 'fail') borderCol = 'border-amber-500';
            img.className = `w-16 h-16 rounded border-2 ${borderCol} object-cover`;
            const badge = document.createElement('div');
            badge.className = 'absolute bottom-0 left-0 right-0 bg-black/70 text-[8px] text-center py-0.5 truncate';
            badge.textContent = face.status === 'match' ? 'MATCH' : (face.score > 0 ? `${face.score}%` : '???');
            container.appendChild(img);
            container.appendChild(badge);
            debugCrops.appendChild(container);
        }
    });
}

function connectWebSocket() {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
        reconnectAttempts = 0;
        statusBadge.textContent = '🟢 System Active';
        statusBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/50';
        document.getElementById('ws-status').textContent = 'Connected';
        logToTerminal("WebSocket Connected. AI Core active.");
        pingInterval = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'heartbeat' })); }, 10000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'registration_status') {
            isProcessing = false;

            if (data.progress > regProgress) {
                initAudio();
                playTone(800, 'sine', 0.1);
                flashAlpha = 0.5;
            }

            regProgress = data.progress;
            regSubtext.textContent = `${data.message}`;

            if (regProgress < 4) {
                regInstruction.textContent = "Look Straight at the Dot";
                targetX = overlayCanvas.width / 2;
            } else if (regProgress >= 4 && regProgress < 8) {
                regInstruction.textContent = "Follow the Dot (Left Profile)";
                targetX = overlayCanvas.width * 0.8;
            } else if (regProgress >= 8 && regProgress < 12) {
                regInstruction.textContent = "Follow the Dot (Right Profile)";
                targetX = overlayCanvas.width * 0.2;
            }

            if (regProgress >= REQUIRED_REG_FRAMES) {
                regInstruction.textContent = "Processing 3D Neural Profile...";
                ws.send(JSON.stringify({ type: 'finish_registration' }));
            }
        } else if (data.type === 'registration_waiting') {
            isProcessing = false;
            regSubtext.textContent = data.message;
            logToTerminal(`⏳ ${data.message}`);
        } else if (data.type === 'registration_success') {
            playTone(1200, 'triangle', 0.4, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(`✅ ${data.message}`);
            alert(data.message);
        } else if (data.type === 'registration_error') {
            playTone(200, 'sawtooth', 0.5, 0.2);
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(`❌ ${data.message}`);
            alert(data.message);
        }

        else if (data.type === 'attendance') {
            currentlyVisible[data.name] = Date.now();
            renderPresenceList();
            addConfirmedEntry(data.name, data.time);
        } else if (data.type === 'ready') {
            isProcessing = false;

            if (data.debug) {
                const debugMsg = data.debug;
                if (debugMsg.includes('Capturing') || debugMsg.includes('Scanning') || debugMsg.includes('YOLOv8')) {
                    logToTerminal(`📡 ${debugMsg}`);
                } else if (debugMsg.includes('detected') || debugMsg.includes('Face')) {
                    logToTerminal(`✅ ${debugMsg}`);
                } else {
                    logToTerminal(debugMsg);
                }
            }

            if (data.faces && data.faces.length > 0) {
                updateTargetFaces(data.faces);
                if (!isRegistering) updateDebugCrops(data.faces);
            } else {
                trackedFaces = {};
                updateDebugCrops([]);
            }
        }
    };

    ws.onclose = () => {
        isProcessing = false;
        clearInterval(pingInterval);
        statusBadge.textContent = '🔴 Disconnected';
        statusBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-red-500/20 text-red-400 border border-red-500/50';
        document.getElementById('ws-status').textContent = 'Offline';
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        logToTerminal(`ERROR: Lost connection. Reconnect in ${timeout/1000}s...`);
        reconnectAttempts++;
        setTimeout(connectWebSocket, timeout);
    };
}

function addConfirmedEntry(name, time) {
    if (confirmedPeople.has(name)) return;
    if (confirmedPeople.size === 0) confirmedList.innerHTML = '';
    confirmedPeople.add(name);
    const div = document.createElement('div');
    div.className = 'bg-emerald-500/10 p-3 rounded-xl border border-emerald-500/20 flex justify-between items-center animate-[slideIn_0.3s_ease-out]';
    div.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-bold">${confirmedPeople.size}</div>
            <div>
                <div class="font-semibold text-slate-200 capitalize tracking-wide">${name.replace(/_/g, ' ')}</div>
                <div class="text-[9px] text-emerald-500 uppercase font-bold tracking-wider">Confirmed Identity</div>
            </div>
        </div>
        <span class="text-[10px] text-emerald-400 font-mono bg-emerald-400/5 px-2 py-1 rounded border border-emerald-400/10">${time}</span>
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
        // ✅ Show "No person" immediately when faces disappear (not after 8 seconds)
        attendanceList.innerHTML = '<div class="text-center text-slate-500 mt-10 text-sm animate-pulse">📷 No person available in camera</div>';
        return;
    }
    attendanceList.innerHTML = ''; 
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    names.forEach(name => {
        const div = document.createElement('div');
        div.className = 'bg-slate-800/80 p-3 rounded-xl border border-emerald-500/50 flex justify-between items-center animate-[slideIn_0.3s_ease-out] shadow-[0_0_10px_rgba(16,185,129,0.1)]';
        div.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-lg shadow-inner">🟢</div>
                <div>
                    <div class="font-semibold text-slate-200 capitalize tracking-wide">${name.replace(/_/g, ' ')}</div>
                    <div class="text-[10px] text-emerald-400 uppercase font-bold tracking-wider">Present Now</div>
                </div>
            </div>
            <span class="text-xs text-emerald-400 font-mono bg-emerald-400/10 px-2 py-1 rounded border border-emerald-400/20">${timeStr}</span>
        `;
        attendanceList.appendChild(div);
    });
}

async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { width: 640, height: 480, facingMode: "user" } 
        });
        video.srcObject = stream;
        video.onloadedmetadata = () => {
            canvas.width = video.videoWidth; canvas.height = video.videoHeight;
            overlayCanvas.width = video.videoWidth; overlayCanvas.height = video.videoHeight;
            requestAnimationFrame(renderLoop);
        };
    } catch (err) {
        statusBadge.textContent = '⚠️ Camera Denied';
        logToTerminal("ERROR: Camera access denied.");
    }
}

// --- THE CONTINUOUS RENDER LOOP ---
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

    if (isRegistering) {
        drawGamifiedScanner();
    } else {
        drawSmoothFaces();
    }

    requestAnimationFrame(renderLoop);
}

connectWebSocket();
startCamera();
// --- DELETE ALL FACES HANDLER ---
document.getElementById('delete-all-btn').addEventListener('click', async () => {
    if (!confirm('?? WARNING: This will permanently delete ALL registered face embeddings from AWS Rekognition. This cannot be undone. Are you absolutely sure?')) {
        return;
    }
    
    logToTerminal('?? Requesting AWS Collection Wipe...');
    try {
        const response = await fetch('/delete_faces', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            logToTerminal('? SUCCESS: AWS Collection wiped clean.');
            alert('Successfully deleted all face embeddings.');
            confirmedPeople.clear();
            confirmedList.innerHTML = '<div class="text-center text-slate-500 mt-10 text-sm">No one confirmed yet.</div>';
        } else {
            logToTerminal('? ERROR: ' + data.message);
            alert('Failed to delete faces: ' + data.message);
        }
    } catch (err) {
        logToTerminal('? NETWORK ERROR: ' + err.message);
        alert('Network error occurred.');
    }
});
