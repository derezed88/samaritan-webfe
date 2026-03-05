#!/usr/bin/env bash
# Run samaritan server with timestamped logging to samaritan.log
cd "$(dirname "$0")"

# Kill any existing instance
fuser -k 8800/tcp 8801/tcp 2>/dev/null || true
sleep 1

source venv/bin/activate

# Unbuffered python, timestamp each line, append to samaritan.log
PYTHONUNBUFFERED=1 python -u samaritan.py 2>&1 | stdbuf -oL awk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0; fflush() }' >> samaritan.log &
PID=$!
echo "$PID" > samaritan.pid
echo "Started PID $PID — logging to samaritan.log"
