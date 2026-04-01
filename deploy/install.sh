#!/usr/bin/env bash
# Install Mesh Dead Drop on the Pi
# Usage: sudo bash deploy/install.sh
set -euo pipefail

APP_DIR="/opt/mesh-deadrop"

echo "=== Mesh Dead Drop — Pi Install ==="

# 1. System packages
echo "[1/4] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

# 2. Copy project files
echo "[2/4] Copying project to $APP_DIR..."
mkdir -p "$APP_DIR"
cp -r deadrop requirements.txt deploy "$APP_DIR/"

# 3. Python venv + deps
echo "[3/4] Setting up Python environment..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# 4. Systemd service
echo "[4/4] Installing systemd service..."
cp "$APP_DIR/deploy/mesh-deadrop.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable mesh-deadrop

chmod +x "$APP_DIR/deploy/start.sh"

# Drop pi-profiles configs if pi-profiles is installed
if [ -d "/opt/pi-profiles/profiles.d" ]; then
    echo "Detected pi-profiles — installing profile configs..."
    cp profiles.d/*.conf /opt/pi-profiles/profiles.d/
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "Services:"
echo "  Mesh Dead Drop → mesh-deadrop.service (http://<pi-ip>:8070)"
echo ""
echo "Usage:"
echo "  sudo systemctl start mesh-deadrop"
echo "  journalctl -u mesh-deadrop -f"
echo "  sudo pi-profiles deadrop"
