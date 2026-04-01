#!/usr/bin/env bash
set -euo pipefail

cd /opt/mesh-deadrop
source .venv/bin/activate

# Auto-detect Meshtastic serial port
PORT=""
for dev in /dev/ttyUSB* /dev/ttyACM*; do
    [ -e "$dev" ] && PORT="$dev" && break
done

if [ -z "$PORT" ]; then
    echo "No Meshtastic device found — starting in simulation mode"
    exec python -m deadrop --simulate
fi

echo "Found Meshtastic device: $PORT"
exec python -m deadrop --port "$PORT"
