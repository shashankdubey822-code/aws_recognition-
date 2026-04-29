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

let ws;
let isProcessing = false;
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

// --- TOAST NOTIFICATION SYSTEM ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
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
        const mirroredX = overlayCanvas.width - x - w;
        
        let color = '#ef4444'; // Red
        if (face.status === 'match') color = '#10b981'; // Green
        else if (face.status === 'verifying') color = '#00d2ff'; // Cyan
        
        const alpha = age > 200 ? Math.max(0, 1 - ((age - 200) / 1000)) : 1;
        
        drawHighTechCorners(overlayCtx, mirroredX, y, w, h, color, alpha);
        
        // Target Box HUD Label
        overlayCtx.globalAlpha = alpha;
        const labelText = face.status === 'verifying' ? `SCANNING...` : `${face.name.replace(/_/g, ' ')} [${face.score.toFixed(1)}%]`;
        
        overlayCtx.font = 'bold 12px "Orbitron", monospace';
        const textWidth = overlayCtx.measureText(labelText).width;
        
        overlayCtx.fillStyle = 'rgba(0,0,0,0.8)';
        overlayCtx.fillRect(mirroredX, y - 25, textWidth + 20, 20);
        
        overlayCtx.fillStyle = color;
        overlayCtx.fillText(labelText, mirroredX + 10, y - 11);
        
        // Decorator lines
        overlayCtx.beginPath();
        overlayCtx.moveTo(mirroredX, y - 5);
        overlayCtx.lineTo(mirroredX - 20, y - 25);
        overlayCtx.lineTo(mirroredX - 20, y - 50);
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
            
            img.className = `w-14 h-14 rounded-md border-2 ${borderCol} object-cover`;
            
            const badge = document.createElement('div');
            badge.className = 'absolute bottom-0 left-0 right-0 bg-black/80 text-[8px] text-center py-0.5 truncate text-white font-mono';
            badge.textContent = face.status === 'match' ? 'VERIFIED' : (face.status === 'verifying' ? 'SCANNING' : 'UNKNOWN');
            
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

        if (data.type === 'registration_status') {
            isProcessing = false;

            if (data.progress > regProgress) {
                initAudio();
                playTone(1000, 'sine', 0.1);
                flashAlpha = 0.5;
            }

            regProgress = data.progress;
            regSubtext.textContent = `${data.message}`;

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
            renderPresenceList();
            addConfirmedEntry(data.name, data.time);
            showToast(`Clearance Granted: ${data.name.replace(/_/g, ' ')}`, "success");
            playTone(1500, 'sine', 0.1);
            logToTerminal(`Clearance Granted: ${data.name}`, "success");
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
        showToast("Camera access denied", "error");
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
