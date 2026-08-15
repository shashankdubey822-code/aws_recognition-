#!/bin/bash
# ====================================================================
# Nexus.AI — Automated Raspberry Pi Setup Script
# Run on Raspberry Pi: bash setup-pi.sh
# ====================================================================

set -e

echo "🚀 Setting up Nexus.AI Raspberry Pi Edge Client..."
echo "================================================="

# 1. Update system packages
echo "📦 Updating system packages..."
sudo apt update
sudo apt install -y python3-pip python3-dev git libcamera-tools v4l-utils

# 2. Setup project directory
PROJECT_DIR="$HOME/nexus-attendance"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 3. Setup Virtual Environment
echo "🐍 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Install Python Dependencies
echo "📦 Installing required Python libraries..."
pip install --upgrade pip
pip install websockets opencv-python-headless

# 5. Download/Ensure rpi_streamer.py is present
if [ ! -f "rpi_streamer.py" ]; then
    echo "📥 Downloading latest rpi_streamer.py..."
    curl -sSL https://huggingface.co/spaces/vrfefavr/Hugging_Face/raw/main/rpi_streamer.py -o rpi_streamer.py
fi

# 6. Test Camera Hardware
echo ""
echo "📸 Testing camera availability..."
python3 << 'PYEOF'
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✅ Camera is detected and ready (Index 0).")
    cap.release()
else:
    print("⚠️ No USB camera found on index 0. Check camera connection or libcamera.")
PYEOF

echo ""
echo "================================================="
echo "✅ Setup Complete!"
echo "To run the Raspberry Pi edge streaming client:"
echo "   source venv/bin/activate"
echo "   python3 rpi_streamer.py --url wss://vrfefavr-hugging-face.hf.space/ws --interval 30"
echo "================================================="
