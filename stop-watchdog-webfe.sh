#!/usr/bin/env bash
# stop-watchdog-webfe.sh - stop the WebFE health watchdog started by watchdog-webfe.sh
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/watchdog-webfe.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No watchdog PID file - not running (or already stopped)."
    exit 0
fi

PID=$(cat "$PID_FILE" 2>/dev/null || true)
if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    echo "Stopped WebFE watchdog (PID $PID)."
else
    echo "Watchdog PID $PID not running - clearing stale PID file."
fi
rm -f "$PID_FILE"
