#!/usr/bin/env bash
# Install Mesh Dead Drop on the Pi. Idempotent and non-interactive.
# Does NOT enable the service at boot — pi-profiles starts it.
# Usage: sudo bash deploy/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="/opt/mesh-deadrop"
DATA_DIR="/var/lib/mesh-deadrop"
ENV_FILE="/etc/mesh-deadrop.env"

echo "=== Mesh Dead Drop — Pi Install ==="

echo "[1/5] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "[2/5] Copying project to $APP_DIR..."
mkdir -p "$APP_DIR" "$DATA_DIR"
rm -rf "$APP_DIR/deadrop"
cp -r "$REPO_DIR/deadrop" "$REPO_DIR/requirements.txt" "$REPO_DIR/deploy" "$REPO_DIR/profiles.d" "$APP_DIR/"
chmod +x "$APP_DIR/deploy/start.sh"
# Move a database left by older installs into the data dir
if [ -f "$APP_DIR/messages.db" ] && [ ! -f "$DATA_DIR/messages.db" ]; then
    mv "$APP_DIR/messages.db" "$DATA_DIR/messages.db"
fi

echo "[3/5] Setting up Python environment..."
[ -x "$APP_DIR/.venv/bin/python" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

echo "[4/5] Config..."
if [ ! -f "$ENV_FILE" ]; then
    install -m 600 "$REPO_DIR/deploy/mesh-deadrop.env.example" "$ENV_FILE"
    echo "Created $ENV_FILE"
fi

echo "[5/5] Installing systemd service (not enabled at boot — pi-profiles starts it)..."
cp "$REPO_DIR/deploy/mesh-deadrop.service" /etc/systemd/system/
systemctl daemon-reload

if [ -d "/opt/pi-profiles/profiles.d" ]; then
    cp "$REPO_DIR/profiles.d/"*.conf /opt/pi-profiles/profiles.d/
    echo "Installed pi-profiles profile: mesh-deadrop"
fi

echo ""
echo "=== Install complete ==="
echo "  Dashboard: http://<pi-ip>:8070"
echo "  Start:     sudo pi-profiles mesh-deadrop     (or: sudo systemctl start mesh-deadrop)"
echo "  Logs:      journalctl -u mesh-deadrop -f"
echo "  The radio is used through meshbus, so mesh-bridge (blufor-tracker) must be running."
