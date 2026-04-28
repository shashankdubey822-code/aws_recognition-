#!/bin/bash
# Raspberry Pi Setup Script for AWS Rekognition Face Detection
# Run on Raspberry Pi: bash setup-pi.sh

set -e  # Exit on error

echo "🚀 AWS Rekognition Raspberry Pi Setup"
echo "======================================"
echo ""

# 1. Update system
echo "📦 Updating system packages..."
sudo apt update
sudo apt upgrade -y

# 2. Install required system dependencies
echo "📦 Installing system dependencies..."
sudo apt install -y \
    python3-pip \
    python3-dev \
    git \
    libopenblas-dev \
    libatlas-base-dev \
    libjasper-dev \
    libtiff-dev \
    libjasper1 \
    libharfbuzz0b \
    libwebp6 \
    libtiff5 \
    libjasper1 \
    libharfbuzz0b \
    libwebp6 \
    libopenjp2-7 \
    libtiff5 \
    libharfbuzz0b

# 3. Create project directory
PROJECT_DIR="$HOME/aws-rekognition"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📁 Creating project directory: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 4. Clone or download the project
echo "📥 Setting up project files..."
if [ ! -f "pi_client.py" ]; then
    echo "   First run - copying files..."
    # You can clone from a repo or copy files manually
    # For now, assume files are already present
fi

# 5. Create Python virtual environment
echo "🐍 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# 6. Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip setuptools wheel
pip install -r requirements-pi.txt

# 7. Create .env file
echo "🔐 Setting up environment variables..."
if [ ! -f ".env" ]; then
    cat > .env << EOF
# Hugging Face API Token
HF_TOKEN=your_hf_token_here

# HF Space WebSocket URL
HF_SPACE_URL=https://vrfefavr-hugging-face.hf.space
WS_URL=wss://vrfefavr-hugging-face.hf.space/ws
EOF
    echo "   ✅ Created .env file"
else
    echo "   ⚠️  .env already exists"
fi

# 8. Test camera
echo ""
echo "📸 Testing camera..."
python3 << 'PYEOF'
try:
    import cv2
    print("✅ OpenCV imported successfully")
    
    try:
        from picamera2 import Picamera2
        print("✅ picamera2 available (CSI camera)")
    except ImportError:
        print("⚠️  picamera2 not available, will try USB camera")
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("✅ USB camera found")
            cap.release()
        else:
            print("❌ No USB camera detected")
except Exception as e:
    print(f"❌ Error: {e}")
PYEOF

# 9. Optional: Create systemd service for auto-start
echo ""
read -p "Setup auto-start on boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📋 Creating systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/aws-rekognition.service"
    
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=AWS Rekognition Pi Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/pi_client.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable aws-rekognition
    echo "✅ Service installed. Start with: sudo systemctl start aws-rekognition"
    echo "   Check status: sudo systemctl status aws-rekognition"
    echo "   View logs: sudo journalctl -u aws-rekognition -f"
fi

echo ""
echo "======================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your HF_TOKEN"
echo "2. Test connection: python3 pi_client.py"
echo "3. Check: https://huggingface.co/spaces/vrfefavr/Hugging_Face"
echo ""
echo "Troubleshooting:"
echo "• Camera not detected: ls /dev/video* or check with v4l2-ctl"
echo "• Connection issues: ping huggingface.co"
echo "• Module errors: pip install --upgrade opencv-python-headless"
echo ""
