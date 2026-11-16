#!/usr/bin/env bash
# Manual launcher. Default: meshbus (needs mesh-bridge running).
#   deploy/start.sh                      # meshbus
#   deploy/start.sh --simulate           # fake activity, no radio
#   deploy/start.sh --serial /dev/ttyUSB0  # standalone, radio direct (stop mesh-bridge first)
set -euo pipefail

cd /opt/mesh-deadrop
source .venv/bin/activate
[ -f /etc/mesh-deadrop.env ] && set -a && . /etc/mesh-deadrop.env && set +a

exec python -m deadrop "$@"
