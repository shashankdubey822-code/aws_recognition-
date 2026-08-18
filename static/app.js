const video = document.getElementById('videoElement');
const canvas = document.getElementById('canvasElement');
const ctx = canvas.getContext('2d', { willReadFrequently: true });
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const confirmedList = document.getElementById('confirmed-list');
const terminalLogs = document.getElementById('terminal-logs');
const cameraSelect = document.getElementById('camera-select');
const fpsCounter = document.getElementById('fps-counter');

// --- REGISTRATION UI ELEMENTS ---
const addStudentBtn = document.getElementById('add-student-btn');
const modalBackdrop = document.getElementById('modal-backdrop');
const cancelBtn = document.getElementById('cancel-btn');
const startScanBtn = document.getElementById('start-scan-btn');
const studentNameInput = document.getElementById('student-name-input');
const studentRollInput = document.getElementById('student-roll-input');
const regFormView = document.getElementById('reg-form-view');
const regScanView = document.getElementById('reg-scan-view');

const regVideoElement = document.getElementById('regVideoElement');
const regCanvasElement = document.getElementById('regCanvasElement');
const regOverlayCanvas = document.getElementById('regOverlayCanvas');
const regCtx = regCanvasElement ? regCanvasElement.getContext('2d', { willReadFrequently: true }) : null;

const regProgressBar = document.getElementById('reg-progress-bar');
const regProgressPercent = document.getElementById('reg-progress-percent');
const regLiveStatusLabel = document.getElementById('reg-live-status-label');
const regDirectionIndicator = document.getElementById('reg-direction-indicator');
const regDirectionText = document.getElementById('reg-direction-text');
const regAngleCounter = document.getElementById('reg-angle-counter');
const regDiagLog = document.getElementById('reg-diag-log');
const regErrorBox = document.getElementById('reg-error-box');
const regErrorTitle = document.getElementById('reg-error-title');
const regErrorMessage = document.getElementById('reg-error-message');
const regRetryBtn = document.getElementById('reg-retry-btn');
const regSystemPing = document.getElementById('reg-system-ping');

// --- SESSION MANAGEMENT UI ELEMENTS ---
const startSessionBtn = document.getElementById('start-session-btn');
const stopSessionBtn = document.getElementById('stop-session-btn');
const turboToggleBtn = document.getElementById('turbo-toggle-btn');
const turboLabel = document.getElementById('turbo-label');
const turboIcon = document.getElementById('turbo-icon');
const sessionDurationSelect = document.getElementById('session-duration-select');
const sessionTargetDeviceSelect = document.getElementById('session-target-device-select');
const sessionTimerBox = document.getElementById('session-timer-box');
const sessionTimerDisplay = document.getElementById('session-timer-display');
const sessionStatusLabel = document.getElementById('session-status-label');
const sessionIndicator = document.getElementById('session-indicator');
const sessionPresentCount = document.getElementById('session-present-count');

let isTurboModeActive = false;
const statSessionStatus = document.getElementById('stat-session-status');
const statTargetNode = document.getElementById('stat-target-node');
const statActivePis = document.getElementById('stat-active-pis');
const ledgerSessionIdLabel = document.getElementById('ledger-session-id-label');

// --- TABS & VIEWS ---
const tabDashboardBtn = document.getElementById('tab-dashboard-btn');
const tabDevicesBtn = document.getElementById('tab-devices-btn');
const tabEventsBtn = document.getElementById('tab-events-btn');
const viewDashboard = document.getElementById('view-dashboard');
const viewDevices = document.getElementById('view-devices');
const viewEvents = document.getElementById('view-events');
const activeDevicesBadge = document.getElementById('active-devices-badge');

// --- 4K EVENT SCANNER ELEMENTS ---
const eventNameInput = document.getElementById('event-name-input');
const eventDateInput = document.getElementById('event-date-input');
const eventDeptInput = document.getElementById('event-dept-input');
const eventDropzone = document.getElementById('event-dropzone');
const eventFileInput = document.getElementById('event-file-input');
const eventFileCountBadge = document.getElementById('event-file-count-badge');
const eventFilePreviews = document.getElementById('event-file-previews');
const eventStartBtn = document.getElementById('event-start-btn');
const eventUploadPanel = document.getElementById('event-upload-panel');
const eventProcessingHud = document.getElementById('event-processing-hud');
const eventResultsPanel = document.getElementById('event-results-panel');
const eventHudStatusLabel = document.getElementById('event-hud-status-label');
const eventHudProgressPercent = document.getElementById('event-hud-progress-percent');
const eventHudProgressBar = document.getElementById('event-hud-progress-bar');
const eventDiagLogs = document.getElementById('event-diag-logs');
const eventStatPhotos = document.getElementById('event-stat-photos');
const eventStatFaces = document.getElementById('event-stat-faces');
const eventStatAttendees = document.getElementById('event-stat-attendees');
const eventStatEmail = document.getElementById('event-stat-email');
const eventDownloadExcelBtn = document.getElementById('event-download-excel-btn');
const eventNewScanBtn = document.getElementById('event-new-scan-btn');
const eventAttendeesTbody = document.getElementById('event-attendees-tbody');

let selectedEventFiles = [];

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
let regStream = null;
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
let regLoopAnimationId = null;

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
            <h4 class="text-xs font-bold uppercase text-slate-900 font-mono">${type}</h4>
            <p class="text-xs text-slate-600 font-sans">${message}</p>
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
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    
    let colorClass = 'text-slate-300';
    let prefix = '[-]';
    if (type === 'error' || msg.includes('ERROR') || msg.includes('Conflict')) { colorClass = 'text-rose-400 font-bold'; prefix = '[!]'; }
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

// --- DIAGNOSTIC REGISTRATION SUITE HELPERS ---
function setDiagStep(stepNum, status, description = null) {
    const stepElem = document.getElementById(`diag-step-${stepNum}`);
    const iconElem = document.getElementById(`diag-icon-${stepNum}`);
    const badgeElem = document.getElementById(`diag-badge-${stepNum}`);
    const descElem = document.getElementById(`diag-desc-${stepNum}`);

    if (!stepElem || !badgeElem) return;

    if (description && descElem) {
        descElem.textContent = description;
    }

    if (status === 'pending') {
        stepElem.className = "p-2.5 rounded-xl border border-slate-200 bg-white/90 flex items-center justify-between transition-all";
        if (iconElem) iconElem.textContent = "⏳";
        badgeElem.className = "text-[10px] font-mono px-2 py-0.5 rounded-lg bg-slate-100 text-slate-600 font-bold";
        badgeElem.textContent = "PENDING";
    } else if (status === 'running') {
        stepElem.className = "p-2.5 rounded-xl border border-sky-300 bg-sky-50/80 ring-2 ring-sky-100 flex items-center justify-between transition-all animate-pulse";
        if (iconElem) iconElem.textContent = "🔄";
        badgeElem.className = "text-[10px] font-mono px-2 py-0.5 rounded-lg bg-sky-100 text-sky-700 font-bold";
        badgeElem.textContent = "CHECKING...";
    } else if (status === 'success') {
        stepElem.className = "p-2.5 rounded-xl border border-emerald-300 bg-emerald-50/80 flex items-center justify-between transition-all";
        if (iconElem) iconElem.textContent = "✅";
        badgeElem.className = "text-[10px] font-mono px-2 py-0.5 rounded-lg bg-emerald-100 text-emerald-800 font-bold";
        badgeElem.textContent = "VERIFIED ✓";
    } else if (status === 'error') {
        stepElem.className = "p-2.5 rounded-xl border border-rose-300 bg-rose-50/80 ring-2 ring-rose-100 flex items-center justify-between transition-all";
        if (iconElem) iconElem.textContent = "❌";
        badgeElem.className = "text-[10px] font-mono px-2 py-0.5 rounded-lg bg-rose-100 text-rose-700 font-bold";
        badgeElem.textContent = "FAILED";
    }
}

function appendDiagLog(msg, type = 'info') {
    if (!regDiagLog) return;
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const div = document.createElement('div');
    
    let color = 'text-slate-300';
    if (type === 'error') color = 'text-rose-400 font-bold';
    else if (type === 'warning') color = 'text-amber-300';
    else if (type === 'success') color = 'text-emerald-400 font-bold';

    div.className = `${color} flex items-center gap-1.5`;
    div.innerHTML = `<span class="text-slate-500">[${time}]</span> <span>${msg}</span>`;
    regDiagLog.appendChild(div);
    regDiagLog.scrollTop = regDiagLog.scrollHeight;
}

function resetDiagChecklist() {
    for (let i = 1; i <= 6; i++) {
        setDiagStep(i, 'pending');
    }
    if (regProgressPercent) regProgressPercent.textContent = '0%';
    if (regProgressBar) regProgressBar.style.width = '0%';
    if (regAngleCounter) regAngleCounter.textContent = '0';
    if (regDirectionText) regDirectionText.textContent = 'LOOK STRAIGHT';
    if (regDirectionIndicator) regDirectionIndicator.textContent = '🎯';
    if (regErrorBox) regErrorBox.classList.add('hidden');
    if (regDiagLog) regDiagLog.innerHTML = '<div>[SYSTEM] Diagnostic engine standby. Ready for scan.</div>';
}

// --- TOP TABS SWITCHER (LIGHT GLASS 3-WAY) ---
function switchMainTab(activeTab) {
    // Reset all tabs
    if (tabDashboardBtn) tabDashboardBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all";
    if (tabDevicesBtn) tabDevicesBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5";
    if (tabEventsBtn) tabEventsBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5";

    if (viewDashboard) viewDashboard.classList.add('hidden');
    if (viewDevices) viewDevices.classList.add('hidden');
    if (viewEvents) viewEvents.classList.add('hidden');

    if (activeTab === 'DASHBOARD') {
        if (tabDashboardBtn) tabDashboardBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold transition-all bg-white text-sky-700 shadow-sm border border-slate-200/80";
        if (viewDashboard) viewDashboard.classList.remove('hidden');
    } else if (activeTab === 'DEVICES') {
        if (tabDevicesBtn) tabDevicesBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold transition-all bg-white text-sky-700 shadow-sm border border-slate-200/80 flex items-center gap-1.5";
        if (viewDevices) viewDevices.classList.remove('hidden');
        renderDevicesView();
    } else if (activeTab === 'EVENTS') {
        if (tabEventsBtn) tabEventsBtn.className = "px-3.5 sm:px-4 py-1.5 rounded-lg text-xs font-mono font-bold transition-all bg-white text-indigo-700 shadow-sm border border-slate-200/80 flex items-center gap-1.5";
        if (viewEvents) viewEvents.classList.remove('hidden');
    }
}

if (tabDashboardBtn) tabDashboardBtn.addEventListener('click', () => switchMainTab('DASHBOARD'));
if (tabDevicesBtn) tabDevicesBtn.addEventListener('click', () => switchMainTab('DEVICES'));
if (tabEventsBtn) tabEventsBtn.addEventListener('click', () => switchMainTab('EVENTS'));

// --- 4K EVENT SCANNER CONTROLLER ---
function appendEventLog(msg, colorClass = "text-slate-300") {
    if (!eventDiagLogs) return;
    const div = document.createElement('div');
    div.className = colorClass;
    div.innerHTML = `<span class="text-slate-500 font-mono">[${new Date().toLocaleTimeString()}]</span> ${msg}`;
    eventDiagLogs.appendChild(div);
    eventDiagLogs.scrollTop = eventDiagLogs.scrollHeight;
}

function handleEventFilesSelected(files) {
    if (!files || files.length === 0) return;
    selectedEventFiles = Array.from(files);

    if (eventFileCountBadge) {
        eventFileCountBadge.textContent = `${selectedEventFiles.length} Photos Selected`;
        eventFileCountBadge.className = "text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 border border-sky-200";
    }

    if (eventStartBtn) {
        eventStartBtn.disabled = false;
    }

    if (eventFilePreviews) {
        eventFilePreviews.innerHTML = '';
        eventFilePreviews.classList.remove('hidden');

        selectedEventFiles.forEach((file, idx) => {
            const card = document.createElement('div');
            card.className = "relative rounded-xl overflow-hidden aspect-video bg-slate-900 border border-slate-200 shadow-sm group";
            
            const img = document.createElement('img');
            img.className = "w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-all";
            img.src = URL.createObjectURL(file);
            
            const badge = document.createElement('span');
            badge.className = "absolute bottom-1 left-1 text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-slate-900/80 text-white truncate max-w-[90%]";
            badge.textContent = `#${idx + 1} ${(file.size / (1024 * 1024)).toFixed(1)}MB`;

            card.appendChild(img);
            card.appendChild(badge);
            eventFilePreviews.appendChild(card);
        });
    }
}

if (eventDropzone && eventFileInput) {
    eventDropzone.onclick = () => eventFileInput.click();
    eventFileInput.onchange = (e) => handleEventFilesSelected(e.target.files);

    eventDropzone.ondragover = (e) => {
        e.preventDefault();
        eventDropzone.classList.add('border-sky-500', 'bg-sky-100/50');
    };
    eventDropzone.ondragleave = () => {
        eventDropzone.classList.remove('border-sky-500', 'bg-sky-100/50');
    };
    eventDropzone.ondrop = (e) => {
        e.preventDefault();
        eventDropzone.classList.remove('border-sky-500', 'bg-sky-100/50');
        if (e.dataTransfer && e.dataTransfer.files) {
            handleEventFilesSelected(e.dataTransfer.files);
        }
    };
}

if (eventStartBtn) {
    eventStartBtn.onclick = async () => {
        if (!selectedEventFiles || selectedEventFiles.length === 0) {
            showToast("Please select at least one 4K event photo.", "error");
            return;
        }

        const eventTitle = (eventNameInput && eventNameInput.value.trim()) || "Annual Faculty Seminar";
        const eventDate = (eventDateInput && eventDateInput.value) || new Date().toISOString().split('T')[0];
        const eventDept = (eventDeptInput && eventDeptInput.value.trim()) || "Main Auditorium";

        const formData = new FormData();
        formData.append("event_name", eventTitle);
        formData.append("event_date", eventDate);
        formData.append("event_dept", eventDept);

        selectedEventFiles.forEach((file) => {
            formData.append("photos", file);
        });

        // Switch to Processing HUD
        if (eventUploadPanel) eventUploadPanel.classList.add('hidden');
        if (eventResultsPanel) eventResultsPanel.classList.add('hidden');
        if (eventProcessingHud) eventProcessingHud.classList.remove('hidden');

        if (eventDiagLogs) eventDiagLogs.innerHTML = '';
        appendEventLog(`🚀 Uploading ${selectedEventFiles.length} photos (${eventTitle}) to 4K SAHI Engine...`, 'text-sky-400 font-bold');

        try {
            const resp = await fetch('/api/event/upload', {
                method: 'POST',
                body: formData
            });
            const resJson = await resp.json();

            if (!resJson.success) {
                appendEventLog(`🔴 Server Error: ${resJson.detail || resJson.message}`, 'text-rose-400 font-bold');
                showToast(resJson.detail || resJson.message, "error");
            } else {
                appendEventLog(`✅ Upload received (${resJson.total_photos} photos). Sliced High-Density inference running...`, 'text-emerald-400');
            }
        } catch (err) {
            appendEventLog(`🔴 Network error during upload: ${err.message}`, 'text-rose-400 font-bold');
            showToast(`Upload failed: ${err.message}`, "error");
        }
    };
}

if (eventNewScanBtn) {
    eventNewScanBtn.onclick = () => {
        selectedEventFiles = [];
        if (eventFileInput) eventFileInput.value = '';
        if (eventFileCountBadge) {
            eventFileCountBadge.textContent = "0 Photos Selected";
            eventFileCountBadge.className = "text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200";
        }
        if (eventFilePreviews) {
            eventFilePreviews.innerHTML = '';
            eventFilePreviews.classList.add('hidden');
        }
        if (eventStartBtn) eventStartBtn.disabled = true;

        if (eventResultsPanel) eventResultsPanel.classList.add('hidden');
        if (eventProcessingHud) eventProcessingHud.classList.add('hidden');
        if (eventUploadPanel) eventUploadPanel.classList.remove('hidden');
    };
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

// --- UPDATE TARGET DEVICE SELECTOR DROPDOWN (CONNECTED ONLY) ---
function updateTargetDeviceDropdown() {
    if (!sessionTargetDeviceSelect) return;
    const currentVal = sessionTargetDeviceSelect.value;
    
    const availableDevices = Object.values(allDevicesMap).filter(d => d.status !== 'disconnected');
    sessionTargetDeviceSelect.innerHTML = '';
    
    if (availableDevices.length === 0) {
        const opt = document.createElement('option');
        opt.value = "";
        opt.textContent = "-- No Active Camera Connected --";
        opt.disabled = true;
        opt.selected = true;
        sessionTargetDeviceSelect.appendChild(opt);
        return;
    }

    availableDevices.forEach((dev, idx) => {
        const opt = document.createElement('option');
        opt.value = dev.device_id;
        opt.textContent = `📍 ${dev.device_name} (${dev.client_ip || '127.0.0.1'})`;
        sessionTargetDeviceSelect.appendChild(opt);
    });

    if (currentVal && availableDevices.some(d => d.device_id === currentVal)) {
        sessionTargetDeviceSelect.value = currentVal;
    } else {
        sessionTargetDeviceSelect.selectedIndex = 0;
    }
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

    updateTargetDeviceDropdown();
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
        devicesCardsList.innerHTML = '<div class="text-center text-slate-400 py-10 font-mono text-xs">No registered edge devices connected.</div>';
        return;
    }

    devices.forEach(dev => {
        const isSelected = dev.device_id === selectedDeviceId;
        const isActive = dev.status === 'active';
        const card = document.createElement('div');
        
        card.className = `p-4 rounded-2xl border transition-all cursor-pointer flex flex-col gap-2 ${
            isSelected 
                ? 'bg-sky-50/90 border-sky-400 shadow-md ring-2 ring-sky-300/30' 
                : 'bg-white/80 border-slate-200 hover:border-sky-300 hover:bg-white shadow-sm'
        }`;
        
        card.onclick = () => {
            selectedDeviceId = dev.device_id;
            renderDevicesView();
        };

        const studentsCount = (dev.verified_students || []).length;
        const stage = dev.stage || 'IDLE';
        let stageBadge = '';

        if (stage === 'CROPPING') {
            stageBadge = '<span class="text-[9px] font-mono px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-bold animate-pulse">✂️ AI CROPPING</span>';
        } else if (stage === 'AWS_MATCHING') {
            stageBadge = '<span class="text-[9px] font-mono px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 font-bold animate-pulse">🔄 AWS SCANNING</span>';
        }

        card.innerHTML = `
            <div class="flex justify-between items-start">
                <div class="flex items-center gap-2.5">
                    <span class="w-2.5 h-2.5 rounded-full ${isActive ? 'bg-emerald-500 animate-ping' : 'bg-slate-400'}"></span>
                    <h4 class="font-bold text-slate-900 font-mono text-xs">${dev.device_name}</h4>
                </div>
                <div class="flex items-center gap-1.5">
                    ${stageBadge}
                    <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                        isActive 
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                            : 'bg-slate-100 text-slate-600 border-slate-200'
                    }">
                        ${isActive ? 'ACTIVE' : 'STANDBY'}
                    </span>
                </div>
            </div>
            <div class="grid grid-cols-3 gap-2 text-[11px] font-mono text-slate-600 mt-1 pt-2 border-t border-slate-200/80">
                <div><span class="text-slate-400">IP:</span> ${dev.client_ip || '127.0.0.1'}</div>
                <div><span class="text-slate-400">Students:</span> <strong class="text-slate-900">${studentsCount}</strong></div>
                <div class="text-right"><span class="text-slate-400">Frames:</span> ${dev.total_frames || 0}</div>
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
            selectedDeviceStatusBadge.className = 'text-xs font-mono font-bold text-purple-700 bg-purple-50 px-3 py-1 rounded-xl border border-purple-200 animate-pulse';
        } else if (dev.stage === 'AWS_MATCHING') {
            selectedDeviceStatusBadge.textContent = '🔄 CONTACTING AWS REKOGNITION...';
            selectedDeviceStatusBadge.className = 'text-xs font-mono font-bold text-sky-700 bg-sky-50 px-3 py-1 rounded-xl border border-sky-200 animate-pulse';
        } else {
            selectedDeviceStatusBadge.textContent = dev.status === 'active' ? 'STREAMING ACTIVE' : 'STANDBY / IDLE';
            selectedDeviceStatusBadge.className = dev.status === 'active' 
                ? 'text-xs font-mono font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-xl border border-emerald-200'
                : 'text-xs font-mono font-bold text-slate-600 bg-slate-100 px-3 py-1 rounded-xl border border-slate-200';
        }
    }
    
    if (selectedDeviceIndicator) {
        selectedDeviceIndicator.className = `w-3 h-3 rounded-full ${dev.status === 'active' ? 'bg-emerald-500 animate-ping' : 'bg-slate-400'}`;
    }

    // Panel A: Verified Students
    if (devPanelStudents) {
        devPanelStudents.innerHTML = '';
        const students = dev.verified_students || [];
        
        if (students.length === 0) {
            devPanelStudents.innerHTML = '<div class="text-center text-slate-400 py-16 font-mono text-xs">No students verified from this specific camera node yet.</div>';
        } else {
            students.forEach((st, idx) => {
                const item = document.createElement('div');
                item.className = 'glass-panel p-3.5 rounded-2xl flex justify-between items-center animate-slideIn shadow-sm';
                item.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold font-mono border border-emerald-200">
                            #${String(idx + 1).padStart(2, '0')}
                        </div>
                        <div>
                            <div class="font-bold text-slate-900 font-mono text-xs">${st.name}</div>
                            <div class="text-[10px] text-sky-700 font-mono font-bold">Roll Number: ${st.roll_number || 'N/A'}</div>
                        </div>
                    </div>
                    <div class="flex items-center gap-3">
                        <span class="text-[10px] text-emerald-700 font-mono font-bold bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200">
                            ${st.time} ✓
                        </span>
                        ${st.photo ? `<img src="${st.photo}" class="w-8 h-8 object-cover rounded-xl border border-slate-200 shadow-sm">` : ''}
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
            devPanelQueue.innerHTML = '<div class="text-center text-slate-400 py-16 font-mono text-xs">No cropped faces currently in FIFO pipeline for this device.</div>';
        } else {
            queue.forEach((item, idx) => {
                let badgeClass = 'bg-sky-50 text-sky-700 border-sky-200';
                let statusIcon = '⏳';
                let statusText = 'IN FIFO QUEUE';

                if (item.status === 'match') {
                    badgeClass = 'bg-emerald-50 text-emerald-700 border-emerald-200 font-bold';
                    statusIcon = '✅';
                    statusText = `MATCH APPROVED (${item.score || 100}%)`;
                } else if (item.status === 'no_match' || item.status === 'unknown') {
                    badgeClass = 'bg-amber-50 text-amber-700 border-amber-200';
                    statusIcon = '❌';
                    statusText = 'NO MATCH IN DB';
                } else if (item.status === 'scanning') {
                    badgeClass = 'bg-sky-50 text-sky-700 border-sky-200 font-bold animate-pulse';
                    statusIcon = '🔄';
                    statusText = 'AWS SCANNING...';
                }

                const card = document.createElement('div');
                card.className = 'glass-panel p-3.5 rounded-2xl flex items-center justify-between gap-3 animate-slideIn shadow-sm';
                card.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="relative w-12 h-12 rounded-xl overflow-hidden border border-slate-200 bg-slate-100 flex-shrink-0 shadow-sm">
                            ${item.crop ? `<img src="${item.crop}" class="w-full h-full object-cover">` : '<div class="w-full h-full flex items-center justify-center text-xs">👤</div>'}
                        </div>
                        <div>
                            <div class="font-bold text-slate-900 font-mono text-xs flex items-center gap-2">
                                <span>${item.name || 'Cropped Face'}</span>
                                ${item.queue_label ? `<span class="text-[9px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 border border-slate-200 font-mono">${item.queue_label}</span>` : ''}
                                ${item.roll_number && item.roll_number !== 'N/A' && item.roll_number !== '...' ? `<span class="text-[10px] text-sky-700 font-normal font-mono">[Roll: ${item.roll_number}]</span>` : ''}
                            </div>
                            <div class="text-[11px] font-mono text-slate-600 mt-0.5">${item.result || 'Processing via AWS Rekognition...'}</div>
                        </div>
                    </div>
                    <div class="flex flex-col items-end gap-1 flex-shrink-0">
                        <span class="text-[10px] font-mono px-2.5 py-0.5 rounded-full border ${badgeClass}">
                            ${statusIcon} ${statusText}
                        </span>
                        <span class="text-[9px] font-mono text-slate-400">${item.time}</span>
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
            devPanelFrames.innerHTML = '<div class="col-span-full text-center text-slate-400 py-16 font-mono text-xs">No raw frames captured for this device yet.</div>';
        } else {
            frames.forEach((frm, idx) => {
                const item = document.createElement('div');
                item.className = 'group relative aspect-video bg-slate-900 rounded-2xl overflow-hidden border border-slate-200 hover:border-sky-500 transition-all cursor-pointer shadow-md';
                item.onclick = () => openLightbox(frm.url, dev.device_name, frm.timestamp, frm.ip || dev.client_ip);
                item.innerHTML = `
                    <img src="${frm.url}" alt="Raw Frame" class="w-full h-full object-cover group-hover:scale-105 transition-all duration-300">
                    <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-3 flex flex-col justify-between">
                        <span class="text-[9px] font-mono text-sky-300 self-end bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm">🔍 ZOOM</span>
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
        devTabStudentsBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 transition-all flex items-center gap-1.5 whitespace-nowrap shadow-sm";
        devTabQueueBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabFramesBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devPanelStudents.classList.remove('hidden');
        devPanelQueue.classList.add('hidden');
        devPanelFrames.classList.add('hidden');
    };

    devTabQueueBtn.onclick = () => {
        currentDevTab = 'QUEUE';
        devTabQueueBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold bg-sky-100 text-sky-800 border border-sky-300 transition-all flex items-center gap-1.5 whitespace-nowrap shadow-sm";
        devTabStudentsBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabFramesBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devPanelQueue.classList.remove('hidden');
        devPanelStudents.classList.add('hidden');
        devPanelFrames.classList.add('hidden');
    };

    devTabFramesBtn.onclick = () => {
        currentDevTab = 'FRAMES';
        devTabFramesBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold bg-sky-100 text-sky-800 border border-sky-300 transition-all flex items-center gap-1.5 whitespace-nowrap shadow-sm";
        devTabStudentsBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
        devTabQueueBtn.className = "px-3.5 py-1.5 rounded-xl text-xs font-mono font-bold text-slate-600 hover:text-slate-900 transition-all flex items-center gap-1.5 whitespace-nowrap";
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
        filterAllBtn.className = "px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-bold";
        filterActiveBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
        filterStoppedBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
        renderDevicesView();
    };
    filterActiveBtn.onclick = () => {
        currentDeviceFilter = 'ACTIVE';
        filterActiveBtn.className = "px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-bold";
        filterAllBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
        filterStoppedBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
        renderDevicesView();
    };
    filterStoppedBtn.onclick = () => {
        currentDeviceFilter = 'STOPPED';
        filterStoppedBtn.className = "px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-bold";
        filterAllBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
        filterActiveBtn.className = "px-2 py-0.5 rounded text-slate-500 hover:text-slate-900";
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

// Dynamic WebSocket URL
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${window.location.host}/ws`;

// --- REGISTRATION SUITE LOGIC ---
if (addStudentBtn) {
    addStudentBtn.addEventListener('click', () => {
        if (modalBackdrop) modalBackdrop.classList.remove('hidden');
        if (regFormView) regFormView.classList.remove('hidden');
        if (regScanView) regScanView.classList.add('hidden');
        if (studentNameInput) {
            studentNameInput.value = '';
            studentNameInput.focus();
        }
        if (studentRollInput) studentRollInput.value = '';
        resetDiagChecklist();
    });
}

if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
        stopRegistrationCamera();
        if (modalBackdrop) modalBackdrop.classList.add('hidden');
    });
}

if (regRetryBtn) {
    regRetryBtn.addEventListener('click', () => {
        if (regErrorBox) regErrorBox.classList.add('hidden');
        resetDiagChecklist();
        startRegistrationSequence();
    });
}

if (startScanBtn) {
    startScanBtn.addEventListener('click', () => {
        startRegistrationSequence();
    });
}

function startRegistrationSequence() {
    const name = studentNameInput ? studentNameInput.value.trim() : "";
    const roll = studentRollInput ? studentRollInput.value.trim() : "";
    
    if (!name) { 
        showToast("Please enter Student Full Name", "error"); 
        if (studentNameInput) studentNameInput.focus();
        return; 
    }
    if (!roll) { 
        showToast("Please enter Student Roll Number / ID", "error"); 
        if (studentRollInput) studentRollInput.focus();
        return; 
    }
    
    if (regFormView) regFormView.classList.add('hidden');
    if (regScanView) regScanView.classList.remove('hidden');
    resetDiagChecklist();

    appendDiagLog(`[INIT] Starting enrolment for ${name} [Roll: ${roll}]`);
    
    // Step 1: Central Server Check
    setDiagStep(1, 'running', 'Verifying active WebSocket link...');
    if (ws && ws.readyState === WebSocket.OPEN) {
        setDiagStep(1, 'success', 'Central Hub link active & authenticated');
        appendDiagLog('[NET] WebSocket authenticated & responsive', 'success');
    } else {
        setDiagStep(1, 'error', 'WebSocket disconnected from central hub');
        appendDiagLog('[NET] ❌ WebSocket offline! Reconnecting...', 'error');
        showRegistrationError('Connection Error', 'Cannot reach central AI server. Please check your internet link or refresh the page.');
        return;
    }

    // Step 2: Optical Camera Initialization
    setDiagStep(2, 'running', 'Accessing local optical sensor / webcam...');
    startRegistrationCamera(name, roll);
}

async function startRegistrationCamera(name, roll) {
    try {
        if (regStream) {
            regStream.getTracks().forEach(t => t.stop());
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }
        });

        regStream = stream;
        regVideoElement.srcObject = stream;

        regVideoElement.onloadedmetadata = () => {
            regCanvasElement.width = regVideoElement.videoWidth;
            regCanvasElement.height = regVideoElement.videoHeight;
            regOverlayCanvas.width = regVideoElement.videoWidth;
            regOverlayCanvas.height = regVideoElement.videoHeight;

            setDiagStep(2, 'success', `Camera ready (${regVideoElement.videoWidth}x${regVideoElement.videoHeight})`);
            appendDiagLog(`[OPTICAL] Sensor online: ${regVideoElement.videoWidth}x${regVideoElement.videoHeight}`, 'success');

            // Step 3: MediaPipe AI Face Pipeline Initialized
            setDiagStep(3, 'running', 'Align face inside the target oval...');
            
            isRegistering = true;
            regProgress = 0;

            ws.send(JSON.stringify({ 
                type: 'start_registration', 
                name: name,
                roll_number: roll
            }));
            
            appendDiagLog(`[AI] Dispatched 3D biometric request for '${name}'`);
            logToTerminal(`[REG] Initiated biometric enrollment for ${name} (Roll: ${roll})`, 'info');

            if (regLoopAnimationId) cancelAnimationFrame(regLoopAnimationId);
            requestAnimationFrame(registrationRenderLoop);
        };
    } catch (err) {
        setDiagStep(2, 'error', 'Camera access denied or unavailable');
        appendDiagLog(`[OPTICAL] ❌ Camera access error: ${err.message}`, 'error');
        showRegistrationError('Camera Access Failed', `Could not access local webcam: ${err.message}. Please allow camera permissions in your browser.`);
    }
}

function registrationRenderLoop() {
    if (!isRegistering) return;

    if (ws && ws.readyState === WebSocket.OPEN && !isProcessing && regVideoElement.readyState >= 2) {
        regCtx.drawImage(regVideoElement, 0, 0, regCanvasElement.width, regCanvasElement.height);
        isProcessing = true;
        
        ws.send(JSON.stringify({
            type: 'register_frame',
            image: regCanvasElement.toDataURL('image/jpeg', 0.8)
        }));
    }

    regLoopAnimationId = requestAnimationFrame(registrationRenderLoop);
}

function stopRegistrationCamera() {
    isRegistering = false;
    if (regLoopAnimationId) {
        cancelAnimationFrame(regLoopAnimationId);
        regLoopAnimationId = null;
    }
    if (regStream) {
        regStream.getTracks().forEach(t => t.stop());
        regStream = null;
    }
    if (regVideoElement) regVideoElement.srcObject = null;
}

function showRegistrationError(title, msg) {
    stopRegistrationCamera();
    if (regErrorBox) {
        regErrorBox.classList.remove('hidden');
        if (regErrorTitle) regErrorTitle.textContent = title;
        if (regErrorMessage) regErrorMessage.textContent = msg;
    }
    showToast(msg, 'error');
}

// --- SESSION MANAGEMENT LOGIC ---
function formatTimerDisplay(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function startCountdown(durationSeconds, targetDevice = "") {
    if (sessionTimerInterval) clearInterval(sessionTimerInterval);
    sessionRemainingSeconds = durationSeconds;
    
    sessionTimerBox.classList.remove('hidden');
    startSessionBtn.classList.add('hidden');
    stopSessionBtn.classList.remove('hidden');
    
    const targetLabel = allDevicesMap[targetDevice]?.device_name || targetDevice || 'Classroom Node';
    if (statTargetNode) statTargetNode.textContent = targetLabel;

    sessionStatusLabel.textContent = `ACTIVE (${targetLabel})`;
    sessionIndicator.className = "inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping";
    if (statSessionStatus) {
        statSessionStatus.textContent = "MONITORING ACTIVE";
        statSessionStatus.className = "text-base font-bold font-mono text-emerald-700";
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
    sessionIndicator.className = "inline-block w-2 h-2 rounded-full bg-slate-400";
    if (statSessionStatus) {
        statSessionStatus.textContent = "STANDBY";
        statSessionStatus.className = "text-base font-bold font-mono text-slate-700";
    }
    if (statTargetNode) statTargetNode.textContent = "None Selected";
}

if (startSessionBtn) {
    startSessionBtn.addEventListener('click', () => {
        const targetDevice = sessionTargetDeviceSelect ? sessionTargetDeviceSelect.value : "";
        
        if (!targetDevice) {
            showToast("No active Raspberry Pi node is connected. Please connect a camera first.", "warning");
            logToTerminal("[SESSION] ❌ Start aborted: No edge camera node selected or online.", "warning");
            return;
        }

        const duration = parseInt(sessionDurationSelect.value) || 60;
        const targetName = allDevicesMap[targetDevice]?.device_name || targetDevice;

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'start_session',
                duration_minutes: duration,
                target_device: targetDevice
            }));
            logToTerminal(`[SESSION] Triggered start command for [${targetName}] (${duration} mins)...`, 'info');
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

// --- ⚡ TURBO MODE CONTROLLER (30 FPS FAST-ACTION CAPTURE) ---
if (turboToggleBtn) {
    turboToggleBtn.addEventListener('click', () => {
        isTurboModeActive = !isTurboModeActive;
        const targetDevice = sessionTargetDeviceSelect ? sessionTargetDeviceSelect.value : "ALL";

        if (isTurboModeActive) {
            turboToggleBtn.className = "px-3.5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white border border-amber-400 font-mono font-bold text-xs tracking-wider transition-all flex items-center gap-1.5 shadow-[0_4px_12px_rgba(245,158,11,0.4)] animate-pulse";
            if (turboLabel) turboLabel.textContent = "TURBO 30FPS: ACTIVE";
            showToast("⚡ Turbo Mode Activated: 30 FPS Optical Flow & Fast Action Burst Active", "success");
            logToTerminal("[TURBO ENGINE] ⚡ Activated 30 FPS High-Speed Optical Flow Burst Mode (8-10 km/h Running Target Capture).", "success");
        } else {
            turboToggleBtn.className = "px-3.5 py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 font-mono font-bold text-xs tracking-wider transition-all flex items-center gap-1.5 shadow-sm";
            if (turboLabel) turboLabel.textContent = "TURBO 30FPS: OFF";
            showToast("Turtle Standard Mode Restored (3s Paced Interval)", "info");
            logToTerminal("[TURBO ENGINE] 🐢 Standard paced interval mode restored (low power).", "info");
        }

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'toggle_turbo_mode',
                device_id: targetDevice || "ALL",
                turbo: isTurboModeActive
            }));
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

// --- NETWORK LATENCY MONITORING ---
let pingStartTime = 0;
let liveLatencyMs = 0;
const modalLatencyBadge = document.getElementById('modal-latency-badge');
const modalLatencyDot = document.getElementById('modal-latency-dot');
const modalLatencyText = document.getElementById('modal-latency-text');
const regTelemetryBrightness = document.getElementById('reg-telemetry-brightness');
const regTelemetryBlur = document.getElementById('reg-telemetry-blur');
const regTelemetryDistance = document.getElementById('reg-telemetry-distance');
const regTelemetryRtt = document.getElementById('reg-telemetry-rtt');

function updateLatencyDisplay(ms) {
    liveLatencyMs = ms;
    if (regTelemetryRtt) regTelemetryRtt.textContent = `${ms} ms`;
    
    if (!modalLatencyBadge || !modalLatencyDot || !modalLatencyText) return;
    
    if (ms < 80) {
        modalLatencyDot.className = 'w-2 h-2 rounded-full bg-emerald-500 animate-pulse';
        modalLatencyBadge.className = 'px-2.5 sm:px-3 py-1 rounded-xl bg-emerald-50 border border-emerald-200 text-[11px] sm:text-xs font-mono font-bold flex items-center gap-1.5 text-emerald-800 transition-all shadow-sm';
        modalLatencyText.textContent = `RTT: ${ms}ms (Optimal)`;
    } else if (ms < 250) {
        modalLatencyDot.className = 'w-2 h-2 rounded-full bg-amber-500 animate-pulse';
        modalLatencyBadge.className = 'px-2.5 sm:px-3 py-1 rounded-xl bg-amber-50 border border-amber-200 text-[11px] sm:text-xs font-mono font-bold flex items-center gap-1.5 text-amber-800 transition-all shadow-sm';
        modalLatencyText.textContent = `RTT: ${ms}ms (Normal)`;
    } else {
        modalLatencyDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
        modalLatencyBadge.className = 'px-2.5 sm:px-3 py-1 rounded-xl bg-rose-50 border border-rose-200 text-[11px] sm:text-xs font-mono font-bold flex items-center gap-1.5 text-rose-800 transition-all shadow-sm';
        modalLatencyText.textContent = `RTT: ${ms}ms (High Lag / Slow Link)`;
    }
}

function sendLatencyPing() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        pingStartTime = performance.now();
        ws.send(JSON.stringify({ type: 'ping', client_time: pingStartTime }));
    }
}

// --- WEBSOCKET CONNECTION ---
function connectWebSocket() {
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        reconnectAttempts = 0;
        const statusElem = document.getElementById('ws-status');
        if (statusElem) {
            statusElem.textContent = 'SYSTEM ONLINE';
            statusElem.className = 'text-xs font-mono text-emerald-700 font-bold tracking-wide';
        }
        if (regSystemPing) regSystemPing.textContent = '● CLOUD LINK ONLINE';
        
        logToTerminal("WebSocket Connected. Central Hub Active (24h IST).", "success");
        showToast("Connected to Central Subsystem", "success");
        
        ws.send(JSON.stringify({ type: 'get_session_status' }));
        ws.send(JSON.stringify({ type: 'get_devices' }));
        sendLatencyPing();
        
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => { 
            if (ws && ws.readyState === WebSocket.OPEN) {
                sendLatencyPing();
            }
        }, 2000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'pong') {
            if (data.client_time) {
                const rtt = Math.max(1, Math.round(performance.now() - data.client_time));
                updateLatencyDisplay(rtt);
            } else if (pingStartTime > 0) {
                const rtt = Math.max(1, Math.round(performance.now() - pingStartTime));
                updateLatencyDisplay(rtt);
            }
            return;
        }

        if (data.type === 'error') {
            isProcessing = false;
            logToTerminal(data.message, "error");
            showToast(data.message, "error");
            return;
        }

        // --- 4K EVENT SCANNER INGESTION MESSAGES ---
        if (data.type === 'event_started') {
            appendEventLog(`🏁 ${data.message}`, 'text-sky-400 font-bold');
            if (eventHudProgressPercent) eventHudProgressPercent.textContent = '5%';
            if (eventHudProgressBar) eventHudProgressBar.style.width = '5%';
            return;
        }

        if (data.type === 'event_progress') {
            const pct = Math.max(5, Math.min(95, Math.round((data.frame_index / data.total_frames) * 90)));
            if (eventHudProgressPercent) eventHudProgressPercent.textContent = `${pct}%`;
            if (eventHudProgressBar) eventHudProgressBar.style.width = `${pct}%`;
            if (eventHudStatusLabel) {
                eventHudStatusLabel.innerHTML = `<span class="w-2.5 h-2.5 rounded-full bg-sky-500 animate-ping"></span> ${data.message}`;
            }
            appendEventLog(`[FRAME ${data.frame_index}/${data.total_frames}] ${data.message}`, data.faces_found ? 'text-indigo-300 font-bold' : 'text-slate-300');
            return;
        }

        if (data.type === 'event_frame_completed') {
            appendEventLog(`✅ Frame ${data.frame_index}/${data.total_frames} complete (${data.faces_detected} faces extracted, ${data.matched_count} cloud verified). Total unique attendees: ${data.current_unique_total}`, 'text-emerald-300 font-bold');
            return;
        }

        if (data.type === 'event_completed') {
            if (eventHudProgressPercent) eventHudProgressPercent.textContent = '100%';
            if (eventHudProgressBar) eventHudProgressBar.style.width = '100%';
            appendEventLog(`🎉 ${data.message}`, 'text-emerald-400 font-bold text-sm');
            showToast(data.message, 'success');

            // Populate Results Panel
            if (eventStatPhotos) eventStatPhotos.textContent = data.total_frames;
            if (eventStatFaces) eventStatFaces.textContent = data.total_faces_detected;
            if (eventStatAttendees) eventStatAttendees.textContent = data.unique_attendees_count;
            if (eventStatEmail) {
                eventStatEmail.textContent = data.email_sent ? 'EMAILED ✓' : 'STANDBY';
                eventStatEmail.className = data.email_sent 
                    ? 'text-xs font-bold font-mono text-emerald-700 mt-2 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200 inline-block'
                    : 'text-xs font-bold font-mono text-slate-500 mt-2 bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200 inline-block';
            }
            if (eventDownloadExcelBtn) {
                eventDownloadExcelBtn.href = data.report_url;
            }

            // Populate Attendees Table
            if (eventAttendeesTbody) {
                eventAttendeesTbody.innerHTML = '';
                if (!data.attendees || data.attendees.length === 0) {
                    eventAttendeesTbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400 font-mono">No matching registered faculty/students found in uploaded event photos.</td></tr>`;
                } else {
                    data.attendees.forEach((att, idx) => {
                        const tr = document.createElement('tr');
                        tr.className = "hover:bg-slate-50 transition-colors";
                        tr.innerHTML = `
                            <td class="p-3 text-center text-slate-400 font-bold">${idx + 1}</td>
                            <td class="p-3 font-bold text-slate-800">${att.roll_number || 'N/A'}</td>
                            <td class="p-3 font-semibold text-slate-900 flex items-center gap-2">
                                <div class="w-6 h-6 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center font-bold text-[10px]">
                                    ${(att.name || 'U').charAt(0)}
                                </div>
                                <span>${att.name}</span>
                            </td>
                            <td class="p-3 text-center font-mono text-emerald-600 font-bold">${att.confidence}%</td>
                            <td class="p-3 text-center text-slate-600 font-mono">${att.seen_count} photo(s)</td>
                            <td class="p-3 text-center">
                                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    PRESENT ✓
                                </span>
                            </td>
                        `;
                        eventAttendeesTbody.appendChild(tr);
                    });
                }
            }

            // Show results view
            if (eventProcessingHud) eventProcessingHud.classList.add('hidden');
            if (eventResultsPanel) eventResultsPanel.classList.remove('hidden');
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
            const targetDev = data.target_device || '';
            startCountdown(data.duration_minutes * 60, targetDev);
            
            confirmedPeople.clear();
            if (confirmedList) confirmedList.innerHTML = '<div class="text-center text-slate-400 mt-20 text-sm font-mono tracking-widest">AWAITING ATTENDANCE (SCANNING VIA RASPBERRY PI)...</div>';
            if (sessionPresentCount) sessionPresentCount.textContent = '0';
            if (ledgerSessionIdLabel) ledgerSessionIdLabel.textContent = `Session: ${data.session_id}`;

            const targetName = allDevicesMap[targetDev]?.device_name || targetDev || 'Classroom Node';
            showToast(`Session started for [${targetName}] (${data.duration_minutes}m)`, "success");
            logToTerminal(`[SESSION] ▶️ Fresh Session Active: ${data.session_id} for [${targetName}] (${data.duration_minutes} mins)`, "success");
            return;
        }

        if (data.type === 'frames_purged') {
            logToTerminal(`[STORAGE] 🧹 ${data.message}`, 'info');
            if (data.devices_cleared) {
                data.devices_cleared.forEach(devId => {
                    if (allDevicesMap[devId]) {
                        allDevicesMap[devId].raw_frames = [];
                        allDevicesMap[devId].cropped_queue = [];
                        allDevicesMap[devId].total_frames = 0;
                    }
                });
                renderDevicesView();
            }
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
                startCountdown(data.remaining_seconds, data.target_device || "");
                if (ledgerSessionIdLabel) ledgerSessionIdLabel.textContent = `Session: ${data.session_id}`;
                logToTerminal(`[SESSION] Resumed active monitoring session (${Math.ceil(data.remaining_seconds/60)} mins remaining)`, "info");
            } else {
                resetSessionUI();
            }
            return;
        }

        // --- ADVANCED ANIMATED REGISTRATION DIAGNOSTIC HANDLERS ---
        if (data.type === 'registration_waiting') {
            isProcessing = false;
            if (regLiveStatusLabel) regLiveStatusLabel.textContent = data.message;

            if (data.telemetry) {
                const b = data.telemetry.brightness;
                const bl = data.telemetry.blur;
                if (regTelemetryBrightness && b !== undefined) {
                    regTelemetryBrightness.textContent = b > 50 ? `Good (${Math.round(b)}%)` : `Dim (${Math.round(b)}%)`;
                    regTelemetryBrightness.className = b > 50 ? 'text-[11px] font-mono font-extrabold text-emerald-600 mt-0.5' : 'text-[11px] font-mono font-extrabold text-amber-600 mt-0.5';
                }
                if (regTelemetryBlur && bl !== undefined) {
                    regTelemetryBlur.textContent = bl > 60 ? `Sharp (${Math.round(bl)})` : `Soft (${Math.round(bl)})`;
                    regTelemetryBlur.className = bl > 60 ? 'text-[11px] font-mono font-extrabold text-sky-600 mt-0.5' : 'text-[11px] font-mono font-extrabold text-amber-600 mt-0.5';
                }
                if (regTelemetryDistance) {
                    regTelemetryDistance.textContent = 'Aligned';
                    regTelemetryDistance.className = 'text-[11px] font-mono font-extrabold text-emerald-600 mt-0.5';
                }
            }

            if (data.direction) {
                if (regDirectionText) regDirectionText.textContent = data.direction === 'CENTER' ? 'LOOK STRAIGHT' : `TURN ${data.direction}`;
                if (regDirectionIndicator) {
                    if (data.direction === 'LEFT') regDirectionIndicator.textContent = '⬅️';
                    else if (data.direction === 'RIGHT') regDirectionIndicator.textContent = '➡️';
                    else if (data.direction === 'UP') regDirectionIndicator.textContent = '⬆️';
                    else if (data.direction === 'DOWN') regDirectionIndicator.textContent = '⬇️';
                    else regDirectionIndicator.textContent = '🎯';
                }
            }

            if (data.step === 'environmental' || data.step === 'face_detection') {
                setDiagStep(3, 'running', data.message);
            } else if (data.step === 'pose_liveness') {
                setDiagStep(3, 'success', 'Face bounding box locked');
                setDiagStep(5, 'running', data.message);
            }
            return;
        }

        if (data.type === 'registration_step_update') {
            isProcessing = false;
            if (data.step === 'conflict_check') {
                setDiagStep(4, data.status, data.message);
                appendDiagLog(`[AWS CHECK] ${data.message}`, data.status);
            }
            return;
        }

        if (data.type === 'registration_status') {
            isProcessing = false;
            regProgress = data.progress;
            
            if (regProgressBar) regProgressBar.style.width = `${regProgress}%`;
            if (regProgressPercent) regProgressPercent.textContent = `${regProgress}%`;
            if (regAngleCounter) regAngleCounter.textContent = data.angle || Math.round((regProgress/100)*20);
            if (regLiveStatusLabel) regLiveStatusLabel.textContent = data.message;

            if (data.telemetry) {
                const b = data.telemetry.brightness;
                const bl = data.telemetry.blur;
                if (regTelemetryBrightness && b !== undefined) {
                    regTelemetryBrightness.textContent = `Optimal (${Math.round(b)}%)`;
                    regTelemetryBrightness.className = 'text-[11px] font-mono font-extrabold text-emerald-600 mt-0.5';
                }
                if (regTelemetryBlur && bl !== undefined) {
                    regTelemetryBlur.textContent = `Clear (${Math.round(bl)})`;
                    regTelemetryBlur.className = 'text-[11px] font-mono font-extrabold text-sky-600 mt-0.5';
                }
            }

            setDiagStep(3, 'success', 'Face geometry & lighting approved');
            setDiagStep(4, 'success', 'No duplicate enrolment conflict');
            setDiagStep(5, 'running', `Indexing Vector Angle ${data.angle || ''}/20...`);
            
            appendDiagLog(`[AWS REKOGNITION] Vector embedding indexed (${regProgress}%)`, 'info');
            return;
        } 
        
        if (data.type === 'registration_success') {
            isProcessing = false;
            stopRegistrationCamera();
            
            if (regProgressBar) regProgressBar.style.width = '100%';
            if (regProgressPercent) regProgressPercent.textContent = '100%';
            if (regAngleCounter) regAngleCounter.textContent = '20';
            if (regLiveStatusLabel) regLiveStatusLabel.textContent = "Enrolment Complete!";

            setDiagStep(5, 'success', '20 Biometric Angles Indexed to AWS Rekognition');
            setDiagStep(6, 'success', 'Persisted to SQLite database & active ledger');
            
            appendDiagLog('[DB] Student credentials committed successfully', 'success');
            logToTerminal(data.message, "success");
            showToast("Student Registered Successfully", "success");

            setTimeout(() => {
                modalBackdrop.classList.add('hidden');
                regFormView.classList.remove('hidden');
                regScanView.classList.add('hidden');
            }, 2500);
            return;
        } 
        
        if (data.type === 'registration_error') {
            isProcessing = false;
            stopRegistrationCamera();
            
            if (data.step === 'conflict_check') {
                setDiagStep(4, 'error', data.message);
            } else {
                setDiagStep(5, 'error', data.message);
            }
            
            appendDiagLog(`[ERROR] ❌ ${data.message}`, 'error');
            logToTerminal(data.message, "error");
            showRegistrationError('Biometric Enrolment Halted', data.message);
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
            statusElem.className = 'text-xs font-mono text-rose-600 font-bold tracking-wide animate-pulse';
        }
        if (regSystemPing) regSystemPing.textContent = '● RECONNECTING...';
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
    div.className = 'glass-panel p-4 rounded-2xl flex justify-between items-center animate-slideIn shadow-sm border border-slate-200/90';
    div.innerHTML = `
        <div class="flex items-center gap-3.5">
            <div class="w-9 h-9 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold font-mono border border-emerald-200">
                #${String(confirmedPeople.size).padStart(2, '0')}
            </div>
            <div>
                <div class="font-bold text-slate-900 font-mono text-sm">${name}</div>
                <div class="text-xs text-sky-700 font-mono font-bold mt-0.5">Roll Number: ${rollNumber}</div>
            </div>
        </div>
        <div class="text-right">
            <span class="text-xs text-emerald-700 font-mono font-bold bg-emerald-50 px-3 py-1 rounded-xl border border-emerald-200">${time} IST ✓</span>
            <div class="text-[10px] text-slate-400 font-mono mt-1">Node: ${deviceName}</div>
        </div>
    `;
    confirmedList.insertBefore(div, confirmedList.firstChild);
}

// --- LOCAL DEMO CAMERA INITIALIZER ---
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
    if (!isDemoRunning) return;

    frameCount++;
    if (Date.now() - lastFpsTime >= 1000) {
        if (fpsCounter) fpsCounter.textContent = frameCount;
        frameCount = 0;
        lastFpsTime = Date.now();
    }

    if (ws && ws.readyState === WebSocket.OPEN && !isProcessing) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        if (isDemoRunning) {
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
                confirmedList.innerHTML = '<div class="text-center text-slate-400 mt-20 text-sm font-mono tracking-widest">AWAITING ATTENDANCE (SCANNING VIA RASPBERRY PI)...</div>';
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
