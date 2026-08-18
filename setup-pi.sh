#!/bin/bash
# ====================================================================
# Anyiiiiie AI — Enterprise Raspberry Pi Provisioning & Daemon Setup
# Supports: Raspberry Pi 3/4/5 / Pi Zero 2W (Debian Bullseye/Bookworm)
# ====================================================================

set -e

# Default Configurations
PROJECT_DIR="${PROJECT_DIR:-$HOME/nexus-attendance}"
SERVER_URL="${SERVER_URL:-wss://vrfefavr-hugging-face.hf.space/ws}"
DEVICE_NAME="${DEVICE_NAME:-Classroom 101}"
ENABLE_SERVICE="${ENABLE_SERVICE:-false}"

echo "================================================="
echo "🚀 Anyiiiiie AI — Raspberry Pi Edge Setup"
echo "Target Dir   : $PROJECT_DIR"
echo "Server WS    : $SERVER_URL"
echo "Device Name  : $DEVICE_NAME"
echo "================================================="

# 1. Install System Dependencies
echo "📦 [1/6] Updating APT and installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv python3-dev git \
    v4l-utils libcamera-tools libcamera-v4l2 \
    libgl1 libglib2.0-0 libatomic1 curl

# 2. Setup Project Directory
echo "📁 [2/6] Setting up project directory..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 3. Create Python Virtual Environment
echo "🐍 [3/6] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install opencv-python-headless websockets numpy psutil

# 4. Copy / Download rpi_streamer.py
if [ ! -f "rpi_streamer.py" ]; then
    echo "📥 [4/6] Downloading latest rpi_streamer.py daemon..."
    curl -sSL https://huggingface.co/spaces/vrfefavr/Hugging_Face/raw/main/rpi_streamer.py -o rpi_streamer.py
fi

# 5. Dual Camera Driver Verification
echo "📸 [5/6] Inspecting camera hardware..."
USE_LIBCAMERIFY=false
if [ -e "/dev/video0" ]; then
    echo "✅ USB V4L2 camera detected at /dev/video0."
    # Configure initial shutter priority if v4l2-ctl is present
    if command -v v4l2-ctl &> /dev/null; then
        echo "⚡ Testing V4L2 shutter priority configuration..."
        v4l2-ctl -d /dev/video0 -c exposure_auto_priority=0 2>/dev/null || true
        v4l2-ctl -d /dev/video0 -c auto_exposure=3 2>/dev/null || true
        v4l2-ctl -d /dev/video0 -c backlight_compensation=1 2>/dev/null || true
        echo "✅ V4L2 shutter priority configured."
    fi
else
    if command -v libcamerify &> /dev/null; then
        echo "ℹ️ CSI camera detected. Using libcamerify compatibility wrapper."
        USE_LIBCAMERIFY=true
    else
        echo "⚠️ Warning: /dev/video0 not found. Check physical connection or CSI camera enablement."
    fi
fi

# Test camera capture
echo "Testing frame capture & sharpness calculation..."
python3 << 'EOF'
import sys, cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    if ret and frame is not None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        print(f"✅ Camera capture SUCCESS: Frame shape {frame.shape}, Laplacian sharpness: {sharpness:.1f}")
    else:
        print("⚠️ Camera opened but frame was empty.")
    cap.release()
else:
    print("ℹ️ Notice: Direct VideoCapture(0) not accessible in this sub-shell (may require CSI libcamerify wrapper).")
EOF

# 6. Generate Systemd Service Template
echo "⚙️ [6/6] Generating systemd service template..."
SERVICE_FILE="/tmp/nexus-streamer.service"
CURRENT_USER=$(whoami)

EXEC_PREFIX=""
if [ "$USE_LIBCAMERIFY" = true ]; then
    EXEC_PREFIX="libcamerify "
fi

cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Anyiiiiie AI Raspberry Pi Camera Streamer Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$EXEC_PREFIX$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/rpi_streamer.py --server "$SERVER_URL" --device-name "$DEVICE_NAME" --turbo --headless
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Generated service file at $SERVICE_FILE"

if [ "$1" == "--install-service" ] || [ "$ENABLE_SERVICE" == "true" ]; then
    echo "Installing systemd service to /etc/systemd/system/nexus-streamer.service..."
    sudo cp "$SERVICE_FILE" /etc/systemd/system/nexus-streamer.service
    sudo systemctl daemon-reload
    sudo systemctl enable nexus-streamer.service
    sudo systemctl restart nexus-streamer.service
    echo "✅ Systemd service installed and started!"
    echo "   Check logs with: journalctl -u nexus-streamer -f"
else
    echo ""
    echo "To install the systemd auto-boot service, run:"
    echo "   sudo cp /tmp/nexus-streamer.service /etc/systemd/system/nexus-streamer.service"
    echo "   sudo systemctl daemon-reload && sudo systemctl enable --now nexus-streamer.service"
fi

echo ""
echo "================================================="
echo "🎉 Anyiiiiie AI Edge Setup Complete!"
echo "To run manually in terminal:"
echo "   source $PROJECT_DIR/venv/bin/activate"
echo "   python3 rpi_streamer.py --server $SERVER_URL --device-name '$DEVICE_NAME' --turbo"
echo "================================================="
