const video = document.getElementById('videoElement');
const canvas = document.getElementById('canvasElement');
const ctx = canvas.getContext('2d', { willReadFrequently: true });
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const confirmedList = document.getElementById('confirmed-list');
const terminalLogs = document.getElementById('terminal-logs');
const debugCrops = document.getElementById('debug-crops');
const cropCount = document.getElementById('crop-count');
const cameraSelect = document.getElementById('camera-select');
const fpsCounter = document.getElementById('fps-counter');

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
const statSessionStatus = document.getElementById('stat-session-status');
const statActivePis = document.getElementById('stat-active-pis');
const ledgerSessionIdLabel = document.getElementById('ledger-session-id-label');

// --- TABS & VIEWS ---
const tabDashboardBtn = document.getElementById('tab-dashboard-btn');
const tabDevicesBtn = document.getElementById('tab-devices-btn');
const viewDashboard = document.getElementById('view-dashboard');
const viewDevices = document.getElementById('view-devices');
const activeDevicesBadge = document.getElementById('active-devices-badge');

// --- DEMO TESTER MODAL ---
const openDemoBtn = document.getElementById('open-demo-btn');
const closeDemoBtn = document.getElementById('close-demo-btn');
const demoModal = document.getElementById('demo-modal');

// --- DEVICES VIEW ELEMENTS ---
const statTotalDevices = document.getElementById('stat-total-devices');
const statActiveDevices = document.getElementById('stat-active-devices');
const statStandbyDevices = document.getElementById('stat-standby-devices');
const statTotalFrames = document.getElementById('stat-total-frames');
const devicesCardsList = document.getElementById('devices-cards-list');

const selectedDeviceName = document.getElementById('selected-device-name');
const selectedDeviceSubmeta = document.getElementById('selected-device-submeta');
const selectedDeviceStatusBadge = document.getElementById('selected-device-status-badge');
const selectedDeviceIndicator = document.getElementById('selected-device-indicator');

// --- TRIPLE TABS INSIDE DEVICE VIEW ---
const devTabStudentsBtn = document.getElementById('dev-tab-students-btn');
const devTabQueueBtn = document.getElementById('dev-tab-queue-btn');
const devTabFramesBtn = document.getElementById('dev-tab-frames-btn');
const devPanelStudents = document.getElementById('dev-panel-students');
const devPanelQueue = document.getElementById('dev-panel-queue');
const devPanelFrames = document.getElementById('dev-panel-frames');

const rawLightbox = document.getElementById('raw-lightbox');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxDeviceTitle = document.getElementById('lightbox-device-title');
const lightboxMetaSubtitle = document.getElementById('lightbox-meta-subtitle');
const lightboxDownloadLink = document.getElementById('lightbox-download-link');
const lightboxCloseBtn = document.getElementById('lightbox-close-btn');
const clearCacheBtn = document.getElementById('clear-cache-btn');

let ws;
let isProcessing = false;
let currentStream = null;
let isFrontCamera = true;
let isDemoRunning = false;
let availableCameras = [];
let frameCount = 0;
let lastFpsTime = Date.now();
let reconnectAttempts = 0;
let pingInterval;

let confirmedPeople = new Set(); 

// --- DEVICES REGISTRY STATE ---
let allDevicesMap = {};
let selectedDeviceId = null;
let currentDeviceFilter = 'ALL';
let currentDevTab = 'STUDENTS'; // 'STUDENTS' | 'QUEUE' | 'FRAMES'

// --- SESSION COUNTDOWN STATE ---
let sessionTimerInterval = null;
let sessionRemainingSeconds = 0;

// --- REGISTRATION STATE ---
let isRegistering = false;
let regProgress = 0;

// --- ADVANCED TRACKING STATE ---
let trackedFaces = {}; 
const LERP_FACTOR = 0.3; 

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    while (container.children.length >= 3) {
        container.removeChild(container.firstChild);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = type === 'error' ? '❌' : (type === 'success' ? '✅' : (type === 'warning' ? '⚠️' : 'ℹ️'));

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

// --- HACKER AUDIT TERMINAL ---
function logToTerminal(msg, type = 'info') {
    if (!terminalLogs) return;
    const div = document.createElement('div');
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    
    let colorClass = 'text-slate-300';
    let prefix = '[-]';
    if (type === 'error' || msg.includes('ERROR') || msg.includes('Conflict')) { colorClass = 'text-red-400 font-bold'; prefix = '[!]'; }
    else if (type === 'warning' || msg.includes('WARNING')) { colorClass = 'text-amber-300 font-bold'; prefix = '[?]'; }
    else if (type === 'success' || msg.includes('Granted') || msg.includes('Approved') || msg.includes('Active')) { colorClass = 'text-emerald-400 font-bold'; prefix = '[+]'; }
    
    div.className = `${colorClass} flex items-start gap-2 break-all`;
    div.innerHTML = `<span class="text-slate-500 select-none">[${time}]</span> <span class="font-bold select-none">${prefix}</span> <span>${msg}</span>`;
    
    terminalLogs.appendChild(div);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
    
    while (terminalLogs.children.length > 50) {
        terminalLogs.removeChild(terminalLogs.firstChild);
    }
}

// --- TOP TABS SWITCHER ---
if (tabDashboardBtn && tabDevicesBtn) {
    tabDashboardBtn.addEventListener('click', () => {
        tabDashboardBtn.className = "px-4 py-1.5 rounded-lg text-xs font-mono font-bold transition-all bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/40 shadow-[0_0_10px_rgba(0,210,255,0.2)]";
        tabDevicesBtn.className = "px-4 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5";
        viewDashboard.classList.remove('hidden');
        viewDevices.classList.add('hidden');
    });

    tabDevicesBtn.addEventListener('click', () => {
        tabDevicesBtn.className = "px-4 py-1.5 rounded-lg text-xs font-mono font-bold transition-all bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/40 shadow-[0_0_10px_rgba(0,210,255,0.2)] flex items-center gap-1.5";
        tabDashboardBtn.className = "px-4 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all";
        viewDevices.classList.remove('hidden');
        viewDashboard.classList.add('hidden');
        renderDevicesView();
    });
}

// --- DEMO TESTER MODAL HANDLERS ---
if (openDemoBtn) {
    openDemoBtn.addEventListener('click', () => {
        demoModal.classList.remove('hidden');
        isDemoRunning = true;
        logToTerminal("Starting local webcam demo tester...", "info");
        startCamera();
    });
}

if (closeDemoBtn) {
    closeDemoBtn.addEventListener('click', () => {
        stopDemoCamera();
    });
}

function stopDemoCamera() {
    isDemoRunning = false;
    demoModal.classList.add('hidden');
    if (currentStream) {
        currentStream.getTracks().forEach(t => t.stop());
        currentStream = null;
    }
    video.srcObject = null;
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    logToTerminal("Local webcam tester stopped and hardware released.", "info");
}

// --- DEVICES VIEW RENDERER ---
function updateDevicesData(devicesList) {
    devicesList.forEach(dev => {
        allDevicesMap[dev.device_id] = dev;
    });
    
    const devices = Object.values(allDevicesMap);
    const activePis = devices.filter(d => d.status === 'active' && d.device_id.startsWith('rpi_')).length;
    const activeCount = devices.filter(d => d.status === 'active').length;
    const standbyCount = devices.filter(d => d.status !== 'active').length;
    const totalFrames = devices.reduce((sum, d) => sum + (d.total_frames || 0), 0);

    if (statActivePis) statActivePis.textContent = activePis;
    if (activeDevicesBadge) activeDevicesBadge.textContent = activeCount;
    if (statTotalDevices) statTotalDevices.textContent = devices.length;
    if (statActiveDevices) statActiveDevices.textContent = activeCount;
    if (statStandbyDevices) statStandbyDevices.textContent = standbyCount;
    if (statTotalFrames) statTotalFrames.textContent = totalFrames;

    if (!selectedDeviceId && devices.length > 0) {
        selectedDeviceId = devices[0].device_id;
    }

    renderDevicesView();
}

function renderDevicesView() {
    if (!devicesCardsList) return;
    
    let devices = Object.values(allDevicesMap);
    if (currentDeviceFilter === 'ACTIVE') {
        devices = devices.filter(d => d.status === 'active');
    } else if (currentDeviceFilter === 'STOPPED') {
        devices = devices.filter(d => d.status !== 'active');
    }

    devicesCardsList.innerHTML = '';
    
    if (devices.length === 0) {
        devicesCardsList.innerHTML = '<div class="text-center text-slate-500 py-10 font-mono text-xs">No registered edge devices connected.</div>';
        return;
    }

    devices.forEach(dev => {
        const isSelected = dev.device_id === selectedDeviceId;
        const isActive = dev.status === 'active';
        const card = document.createElement('div');
        
        card.className = `p-4 rounded-xl border transition-all cursor-pointer flex flex-col gap-2 ${
            isSelected 
                ? 'bg-brand-cyan/15 border-brand-cyan shadow-[0_0_15px_rgba(0,210,255,0.25)]' 
                : 'bg-black/60 border-white/10 hover:border-brand-cyan/40 hover:bg-black/80'
        }`;
        
        card.onclick = () => {
            selectedDeviceId = dev.device_id;
            renderDevicesView();
        };

        const studentsCount = (dev.verified_students || []).length;
        const stage = dev.stage || 'IDLE';
        let stageBadge = '';

        if (stage === 'CROPPING') {
            stageBadge = '<span class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse">✂️ AI CROPPING</span>';
        } else if (stage === 'AWS_MATCHING') {
            stageBadge = '<span class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 animate-pulse">🔄 AWS SCANNING</span>';
        }

        card.innerHTML = `
            <div class="flex justify-between items-start">
                <div class="flex items-center gap-2.5">
                    <span class="w-2.5 h-2.5 rounded-full ${isActive ? 'bg-brand-emerald animate-ping' : 'bg-slate-500'}"></span>
                    <h4 class="font-bold text-white font-mono text-xs">${dev.device_name}</h4>
                </div>
                <div class="flex items-center gap-1.5">
                    ${stageBadge}
                    <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                        isActive 
                            ? 'bg-brand-emerald/20 text-brand-emerald border-brand-emerald/40' 
                            : 'bg-slate-800 text-slate-400 border-slate-700'
                    }">
                        ${isActive ? 'ACTIVE' : 'STANDBY'}
                    </span>
                </div>
            </div>
            <div class="grid grid-cols-3 gap-2 text-[11px] font-mono text-slate-400 mt-1 pt-2 border-t border-white/5">
                <div><span class="text-slate-500">IP:</span> ${dev.client_ip || '127.0.0.1'}</div>
                <div><span class="text-slate-500">Students:</span> ${studentsCount}</div>
                <div class="text-right"><span class="text-slate-500">Frames:</span> ${dev.total_frames || 0}</div>
                <div class="col-span-3 text-[10px] text-slate-500 truncate">Last Active: ${dev.last_seen || 'N/A'}</div>
            </div>
        `;
        
        devicesCardsList.appendChild(card);
    });

    renderSelectedDeviceDetails();
}

function renderSelectedDeviceDetails() {
    const dev = allDevicesMap[selectedDeviceId];
    if (!dev) return;

    if (selectedDeviceName) selectedDeviceName.textContent = dev.device_name;
    if (selectedDeviceSubmeta) selectedDeviceSubmeta.textContent = `IP: ${dev.client_ip} | Registered: ${dev.first_seen} | Total Frames: ${dev.total_frames}`;
    
    if (selectedDeviceStatusBadge) {
        if (dev.stage === 'CROPPING') {
            selectedDeviceStatusBadge.textContent = '✂️ LOCAL AI EXTRACTING FACES...';
            selectedDeviceStatusBadge.className = 'text-xs font-mono text-purple-400 bg-purple-500/10 px-3 py-1 rounded-lg border border-purple-500/30 animate-pulse';
        } else if (dev.stage === 'AWS_MATCHING') {
            selectedDeviceStatusBadge.textContent = '🔄 CONTACTING AWS REKOGNITION...';
            selectedDeviceStatusBadge.className = 'text-xs font-mono text-cyan-400 bg-cyan-500/10 px-3 py-1 rounded-lg border border-cyan-500/30 animate-pulse';
        } else {
            selectedDeviceStatusBadge.textContent = dev.status === 'active' ? 'STREAMING ACTIVE' : 'STANDBY / IDLE';
            selectedDeviceStatusBadge.className = dev.status === 'active' 
                ? 'text-xs font-mono text-brand-emerald bg-brand-emerald/10 px-3 py-1 rounded-lg border border-brand-emerald/30'
                : 'text-xs font-mono text-slate-400 bg-slate-800 px-3 py-1 rounded-lg border border-slate-700';
        }
    }
    
    if (selectedDeviceIndicator) {
        selectedDeviceIndicator.className = `w-3 h-3 rounded-full ${dev.status === 'active' ? 'bg-brand-emerald animate-ping' : 'bg-slate-500'}`;
    }

    // Panel A: Verified Students
    if (devPanelStudents) {
        devPanelStudents.innerHTML = '';
        const students = dev.verified_students || [];
        
        if (students.length === 0) {
            devPanelStudents.innerHTML = '<div class="text-center text-slate-500 py-16 font-mono text-xs">No students verified from this specific camera node yet.</div>';
        } else {
            students.forEach((st, idx) => {
                const item = document.createElement('div');
                item.className = 'bg-black/60 p-3 rounded-xl border border-brand-emerald/30 flex justify-between items-center animate-slideIn';
                item.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-lg bg-brand-emerald/20 text-brand-emerald flex items-center justify-center text-xs font-bold font-mono border border-brand-emerald/40">
                            #${String(idx + 1).padStart(2, '0')}
                        </div>
                        <div>
                            <div class="font-bold text-white font-mono text-xs">${st.name}</div>
                            <div class="text-[10px] text-brand-cyan font-mono font-bold">Roll Number: ${st.roll_number || 'N/A'}</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        <span class="text-[10px] text-brand-emerald font-mono bg-brand-emerald/10 px-2 py-1 rounded border border-brand-emerald/30">
                            ${st.time} ✓
                        </span>
                        ${st.photo ? `<img src="${st.photo}" class="w-8 h-8 object-cover rounded-lg border border-white/20">` : ''}
                    </div>
                `;
                devPanelStudents.appendChild(item);
            });
        }
    }

    // Panel B: Live Cropped Faces & AWS FIFO Queue
    if (devPanelQueue) {
        devPanelQueue.innerHTML = '';
        const queue = dev.cropped_queue || [];

        if (queue.length === 0) {
            devPanelQueue.innerHTML = '<div class="text-center text-slate-500 py-16 font-mono text-xs">No cropped faces currently in FIFO pipeline for this device.</div>';
        } else {
            queue.forEach((item, idx) => {
                let badgeClass = 'bg-blue-500/20 text-blue-400 border-blue-500/30';
                let statusIcon = '⏳';
                let statusText = 'IN FIFO QUEUE';

                if (item.status === 'match') {
                    badgeClass = 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 font-bold';
                    statusIcon = '✅';
                    statusText = `MATCH APPROVED (${item.score || 100}%)`;
                } else if (item.status === 'no_match') {
                    badgeClass = 'bg-amber-500/20 text-amber-400 border-amber-500/30';
                    statusIcon = '❌';
                    statusText = 'NO MATCH IN DB';
                } else if (item.status === 'spoof') {
                    badgeClass = 'bg-red-500/20 text-red-400 border-red-500/30 font-bold';
                    statusIcon = '🛑';
                    statusText = 'SPOOF BLOCKED';
                } else if (item.status === 'scanning') {
                    badgeClass = 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30 animate-pulse';
                    statusIcon = '🔄';
                    statusText = 'AWS SCANNING...';
                }

                const card = document.createElement('div');
                card.className = 'bg-black/60 p-3 rounded-xl border border-white/10 flex items-center justify-between gap-3 animate-slideIn';
                card.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="relative w-12 h-12 rounded-lg overflow-hidden border border-white/20 bg-black flex-shrink-0">
                            ${item.crop ? `<img src="${item.crop}" class="w-full h-full object-cover">` : '<div class="w-full h-full flex items-center justify-center text-xs">👤</div>'}
                        </div>
                        <div>
                            <div class="font-bold text-white font-mono text-xs flex items-center gap-2">
                                <span>${item.name || 'Cropped Face'}</span>
                                ${item.roll_number && item.roll_number !== 'N/A' ? `<span class="text-[10px] text-brand-cyan font-normal font-mono">[Roll: ${item.roll_number}]</span>` : ''}
                            </div>
                            <div class="text-[11px] font-mono text-slate-400 mt-0.5">${item.result || 'Processing via AWS Rekognition...'}</div>
                        </div>
                    </div>
                    <div class="flex flex-col items-end gap-1 flex-shrink-0">
                        <span class="text-[10px] font-mono px-2 py-0.5 rounded border ${badgeClass}">
                            ${statusIcon} ${statusText}
                        </span>
                        <span class="text-[9px] font-mono text-slate-500">${item.time}</span>
                    </div>
                `;
                devPanelQueue.appendChild(card);
            });
        }
    }

    // Panel C: Raw Uncropped Frames
    if (devPanelFrames) {
        devPanelFrames.innerHTML = '';
        const frames = dev.raw_frames || [];
        
        if (frames.length === 0) {
            devPanelFrames.innerHTML = '<div class="col-span-full text-center text-slate-500 py-16 font-mono text-xs">No raw frames captured for this device yet.</div>';
        } else {
            frames.forEach((frm, idx) => {
                const item = document.createElement('div');
                item.className = 'group relative aspect-video bg-black rounded-lg overflow-hidden border border-white/10 hover:border-brand-cyan transition-all cursor-pointer shadow-md';
                item.onclick = () => openLightbox(frm.url, dev.device_name, frm.timestamp, frm.ip || dev.client_ip);
                item.innerHTML = `
                    <img src="${frm.url}" alt="Raw Frame" class="w-full h-full object-cover group-hover:scale-105 transition-all duration-300">
                    <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-2 flex flex-col justify-between">
                        <span class="text-[9px] font-mono text-brand-cyan self-end bg-black/60 px-1.5 py-0.5 rounded">🔍 ZOOM</span>
                        <div class="text-[10px] font-mono text-white">${frm.timestamp}</div>
                    </div>
                `;
                devPanelFrames.appendChild(item);
            });
        }
    }
}

// Triple Tab Switchers Inside Device View
if (devTabStudentsBtn && devTabQueueBtn && devTabFramesBtn) {
    devTabStudentsBtn.onclick = () => {
        currentDevTab = 'STUDENTS';
        devTabStudentsBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold bg-brand-emerald/20 text-brand-emerald border border-brand-emerald/40 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabQueueBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabFramesBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devPanelStudents.classList.remove('hidden');
        devPanelQueue.classList.add('hidden');
        devPanelFrames.classList.add('hidden');
    };

    devTabQueueBtn.onclick = () => {
        currentDevTab = 'QUEUE';
        devTabQueueBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/40 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabStudentsBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabFramesBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devPanelQueue.classList.remove('hidden');
        devPanelStudents.classList.add('hidden');
        devPanelFrames.classList.add('hidden');
    };

    devTabFramesBtn.onclick = () => {
        currentDevTab = 'FRAMES';
        devTabFramesBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/40 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabStudentsBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabQueueBtn.className = "px-3 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-400 hover:text-white transition-all flex items-center gap-1.5 whitespace-nowrap";
        devPanelFrames.classList.remove('hidden');
        devPanelStudents.classList.add('hidden');
        devPanelQueue.classList.add('hidden');
    };
}

// Filter button handlers
const filterAllBtn = document.getElementById('filter-all-devices-btn');
const filterActiveBtn = document.getElementById('filter-active-devices-btn');
const filterStoppedBtn = document.getElementById('filter-stopped-devices-btn');

if (filterAllBtn && filterActiveBtn && filterStoppedBtn) {
    filterAllBtn.onclick = () => {
        currentDeviceFilter = 'ALL';
        filterAllBtn.className = "px-2 py-0.5 rounded bg-brand-cyan/20 text-brand-cyan font-bold";
        filterActiveBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        filterStoppedBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        renderDevicesView();
    };
    filterActiveBtn.onclick = () => {
        currentDeviceFilter = 'ACTIVE';
        filterActiveBtn.className = "px-2 py-0.5 rounded bg-brand-cyan/20 text-brand-cyan font-bold";
        filterAllBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        filterStoppedBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        renderDevicesView();
    };
    filterStoppedBtn.onclick = () => {
        currentDeviceFilter = 'STOPPED';
        filterStoppedBtn.className = "px-2 py-0.5 rounded bg-brand-cyan/20 text-brand-cyan font-bold";
        filterAllBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        filterActiveBtn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white";
        renderDevicesView();
    };
}

// --- LIGHTBOX MODAL HANDLERS ---
function openLightbox(imgUrl, deviceName, timestamp, ip) {
    if (!rawLightbox) return;
    lightboxImg.src = imgUrl;
    lightboxDeviceTitle.textContent = `${deviceName} — Raw Uncropped Frame`;
    lightboxMetaSubtitle.textContent = `Timestamp: ${timestamp} | IP: ${ip} | Full Resolution`;
    lightboxDownloadLink.href = imgUrl;
    rawLightbox.classList.remove('hidden');
}

if (lightboxCloseBtn) {
    lightboxCloseBtn.onclick = () => rawLightbox.classList.add('hidden');
}

if (rawLightbox) {
    rawLightbox.onclick = (e) => {
        if (e.target === rawLightbox) rawLightbox.classList.add('hidden');
    };
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

        modalBackdrop.classList.add('hidden');
        regOverlay.classList.remove('hidden');
        if (regProgressBar) regProgressBar.style.width = '0%';
        
        regInstruction.textContent = "INITIALIZING 3D SCAN";
        regSubtext.textContent = "Align face with camera...";
        
        startCamera().then(() => {
            ws.send(JSON.stringify({ 
                type: 'start_registration', 
                name: name,
                roll_number: roll
            }));
            logToTerminal(`Initiated biometric mapping for ${name} (Roll: ${roll})`, 'info');
        });
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
    if (statSessionStatus) {
        statSessionStatus.textContent = "MONITORING ACTIVE";
        statSessionStatus.className = "text-base font-bold font-mono text-brand-emerald";
    }
    
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
    if (statSessionStatus) {
        statSessionStatus.textContent = "STANDBY";
        statSessionStatus.className = "text-base font-bold font-mono text-slate-400";
    }
}

if (startSessionBtn) {
    startSessionBtn.addEventListener('click', () => {
        const duration = parseInt(sessionDurationSelect.value) || 50;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'start_session',
                duration_minutes: duration
            }));
            logToTerminal(`[SESSION] Triggered start command (${duration} mins) to Raspberry Pis...`, 'info');
        } else {
            showToast("Server connection offline", "error");
        }
    });
}

if (stopSessionBtn) {
    stopSessionBtn.addEventListener('click', () => {
        if (!confirm("Are you sure you want to STOP monitoring? This will immediately compile the Excel sheet and email it to shashankdubey822@gmail.com.")) return;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'stop_session' }));
            logToTerminal(`[SESSION] Manual stop triggered. Dispatching report...`, 'warning');
        }
    });
}

// --- CLEAR RAW FRAME CACHE ---
if (clearCacheBtn) {
    clearCacheBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/clear_frames', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast("Frame cache cleared", "success");
                logToTerminal("Purged stored raw frames cache from server.", "success");
                for (const d in allDevicesMap) {
                    allDevicesMap[d].raw_frames = [];
                    allDevicesMap[d].cropped_queue = [];
                    allDevicesMap[d].total_frames = 0;
                }
                updateDevicesData(Object.values(allDevicesMap));
            }
        } catch (e) {
            showToast("Failed to clear cache", "error");
        }
    });
}

// --- WEBSOCKET CONNECTION ---
function connectWebSocket() {
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        reconnectAttempts = 0;
        const statusElem = document.getElementById('ws-status');
        if (statusElem) {
            statusElem.textContent = 'SYSTEM ONLINE';
            statusElem.className = 'text-xs font-mono text-emerald-400 tracking-wide';
        }
        logToTerminal("WebSocket Connected. Central Hub Active.", "success");
        showToast("Connected to Central Subsystem", "success");
        
        ws.send(JSON.stringify({ type: 'get_session_status' }));
        ws.send(JSON.stringify({ type: 'get_devices' }));
        
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

        // --- DEVICES & RAW FRAMES TELEMETRY ---
        if (data.type === 'devices_update') {
            if (data.devices) {
                updateDevicesData(data.devices);
            }
            return;
        }

        // --- DEVICE STAGE TELEMETRY ANIMATION ---
        if (data.type === 'device_stage_update') {
            const devId = data.device_id;
            if (allDevicesMap[devId]) {
                allDevicesMap[devId].stage = data.stage;
                if (data.stage === 'CROPPING') {
                    logToTerminal(`[${allDevicesMap[devId].device_name}] 📸 Frame Ingested ➔ Local AI Face Detection active...`, 'info');
                } else if (data.stage === 'AWS_MATCHING') {
                    logToTerminal(`[${allDevicesMap[devId].device_name}] 🔄 ${data.message}`, 'info');
                }
            }
            renderDevicesView();
            return;
        }

        // --- LIVE AWS FIFO CROPPED QUEUE UPDATE ---
        if (data.type === 'aws_queue_update') {
            const devId = data.device_id;
            if (allDevicesMap[devId]) {
                allDevicesMap[devId].cropped_queue = data.queue;
            }
            renderSelectedDeviceDetails();
            return;
        }

        if (data.type === 'new_raw_frame') {
            const devId = data.device_id;
            if (allDevicesMap[devId]) {
                if (!allDevicesMap[devId].raw_frames) allDevicesMap[devId].raw_frames = [];
                allDevicesMap[devId].raw_frames.unshift(data.frame);
                if (allDevicesMap[devId].raw_frames.length > 20) allDevicesMap[devId].raw_frames.pop();
                allDevicesMap[devId].total_frames = (allDevicesMap[devId].total_frames || 0) + 1;
                allDevicesMap[devId].last_seen = data.frame.timestamp;
                allDevicesMap[devId].status = 'active';
            }
            updateDevicesData(Object.values(allDevicesMap));
            return;
        }

        // --- SESSION MESSAGE HANDLERS ---
        if (data.type === 'session_started') {
            startCountdown(data.duration_minutes * 60);
            
            confirmedPeople.clear();
            if (confirmedList) confirmedList.innerHTML = '<div class="text-center text-slate-500/50 mt-20 text-sm font-mono tracking-widest">AWAITING ATTENDANCE (SCANNING VIA RASPBERRY PI)...</div>';
            if (sessionPresentCount) sessionPresentCount.textContent = '0';
            if (ledgerSessionIdLabel) ledgerSessionIdLabel.textContent = `Session: ${data.session_id}`;

            showToast(`Session started (${data.duration_minutes}m) — Clean Slate`, "success");
            logToTerminal(`[SESSION] ▶️ Fresh Session Active: ${data.session_id} (${data.duration_minutes} mins)`, "success");
            return;
        }

        if (data.type === 'session_stopped') {
            resetSessionUI();
            showToast(`Session ended! Report emailed to shashankdubey822@gmail.com (${data.total_attendees} students)`, "success");
            logToTerminal(`[SESSION] 🏁 Concluded. Attendees: ${data.total_attendees}. Report emailed to shashankdubey822@gmail.com.`, "success");
            return;
        }

        if (data.type === 'session_status') {
            if (data.active && data.remaining_seconds > 0) {
                startCountdown(data.remaining_seconds);
                if (ledgerSessionIdLabel) ledgerSessionIdLabel.textContent = `Session: ${data.session_id}`;
                logToTerminal(`[SESSION] Resumed active monitoring session (${Math.ceil(data.remaining_seconds/60)} mins remaining)`, "info");
            } else {
                resetSessionUI();
            }
            return;
        }

        // --- REGISTRATION MESSAGES ---
        if (data.type === 'registration_status') {
            isProcessing = false;
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
        
        if (data.type === 'registration_success') {
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "success");
            showToast("Student Registered Successfully", "success");
            if (currentStream && !isDemoRunning) {
                currentStream.getTracks().forEach(t => t.stop());
                currentStream = null;
                video.srcObject = null;
            }
            return;
        } 
        
        if (data.type === 'registration_error') {
            isProcessing = false;
            isRegistering = false;
            regOverlay.classList.add('hidden');
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
            if (currentStream && !isDemoRunning) {
                currentStream.getTracks().forEach(t => t.stop());
                currentStream = null;
                video.srcObject = null;
            }
            return;
        }

        // --- ATTENDANCE VERIFIED ---
        if (data.type === 'attendance') {
            const displayName = data.name;
            const rollNumber = data.roll_number || 'N/A';
            const devId = data.device_id || 'Raspberry Pi';

            addConfirmedEntry(displayName, rollNumber, data.time, devId);
            showToast(`Verified: ${displayName} (${rollNumber})`, "success");
            logToTerminal(`Clearance Granted: ${displayName} [Roll: ${rollNumber}] via ${devId}`, "success");
            
            if (allDevicesMap[devId]) {
                if (!allDevicesMap[devId].verified_students) allDevicesMap[devId].verified_students = [];
                const alreadyInDev = allDevicesMap[devId].verified_students.some(s => s.name === displayName);
                if (!alreadyInDev) {
                    allDevicesMap[devId].verified_students.unshift({
                        name: displayName,
                        roll_number: rollNumber,
                        time: data.time
                    });
                }
                renderDevicesView();
            }
            return;
        }

        // --- FRAME RESULTS (IN DEMO MODE) ---
        if (data.type === 'ready') {
            isProcessing = false;
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
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        setTimeout(connectWebSocket, timeout);
        reconnectAttempts++;
    };
}

function addConfirmedEntry(name, rollNumber, time, deviceName) {
    const key = `${rollNumber}_${name}`;
    if (confirmedPeople.has(key)) return;
    if (confirmedPeople.size === 0) confirmedList.innerHTML = '';
    confirmedPeople.add(key);
    
    if (sessionPresentCount) sessionPresentCount.textContent = confirmedPeople.size;
    
    const div = document.createElement('div');
    div.className = 'bg-brand-emerald/10 p-4 rounded-xl border border-brand-emerald/30 flex justify-between items-center animate-slideIn shadow-[0_0_15px_rgba(16,185,129,0.1)]';
    div.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-brand-emerald/20 text-brand-emerald flex items-center justify-center text-xs font-bold font-mono border border-brand-emerald/50">
                #${String(confirmedPeople.size).padStart(2, '0')}
            </div>
            <div>
                <div class="font-bold text-white tracking-wide font-mono text-sm">${name}</div>
                <div class="text-xs text-brand-cyan font-mono font-bold mt-0.5">Roll Number: ${rollNumber}</div>
            </div>
        </div>
        <div class="text-right">
            <span class="text-xs text-brand-emerald font-mono bg-brand-emerald/10 px-2.5 py-1 rounded border border-brand-emerald/20">${time} ✓</span>
            <div class="text-[10px] text-slate-500 font-mono mt-1">Node: ${deviceName}</div>
        </div>
    `;
    confirmedList.insertBefore(div, confirmedList.firstChild);
}

// --- LOCAL CAMERA INITIALIZER (FOR DEMO & REGISTRATION ONLY) ---
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

        video.onloadedmetadata = () => {
            canvas.width = video.videoWidth; 
            canvas.height = video.videoHeight;
            overlayCanvas.width = video.videoWidth; 
            overlayCanvas.height = video.videoHeight;
            
            populateCameraDevices();
            requestAnimationFrame(renderLoop);
        };
    } catch (err) {
        showToast("Camera access failed or unavailable", "error");
    }
}

async function populateCameraDevices() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        availableCameras = devices.filter(d => d.kind === 'videoinput');
        
        if (cameraSelect) {
            cameraSelect.innerHTML = '';
            availableCameras.forEach((cam, idx) => {
                const option = document.createElement('option');
                option.value = cam.deviceId;
                option.textContent = cam.label || `Camera ${idx + 1}`;
                cameraSelect.appendChild(option);
            });
        }
    } catch (err) {}
}

if (cameraSelect) {
    cameraSelect.addEventListener('change', (e) => {
        if (e.target.value) startCamera(e.target.value);
    });
}

function renderLoop() {
    if (!isDemoRunning && !isRegistering) return;

    frameCount++;
    if (Date.now() - lastFpsTime >= 1000) {
        if (fpsCounter) fpsCounter.textContent = frameCount;
        frameCount = 0;
        lastFpsTime = Date.now();
    }

    if (ws && ws.readyState === WebSocket.OPEN && !isProcessing) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        if (isRegistering) {
            isProcessing = true;
            ws.send(JSON.stringify({ type: 'register_frame', image: canvas.toDataURL('image/jpeg', 0.8) }));
        } else if (isDemoRunning) {
            isProcessing = true;
            ws.send(JSON.stringify({ 
                type: 'frame', 
                device_id: 'web_demo_client',
                device_name: 'Web Browser Demo',
                is_demo: true,
                image: canvas.toDataURL('image/jpeg', 0.7) 
            }));
        }
    }

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
                confirmedList.innerHTML = '<div class="text-center text-slate-500/50 mt-20 text-sm font-mono tracking-widest">AWAITING ATTENDANCE (SCANNING VIA RASPBERRY PI)...</div>';
            }
        } catch (err) {
            logToTerminal(err.message, 'error');
        }
    });
}

const downloadBtn = document.getElementById('download-btn');
if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
        showToast("Exporting Master Attendance Log...", "info");
        const a = document.createElement('a');
        a.href = '/logs';
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });
}

connectWebSocket();
