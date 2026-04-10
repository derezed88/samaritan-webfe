#!/usr/bin/env bash
# Run samaritan server with timestamped logging to samaritan.log
cd "$(dirname "$0")"

HTTP_PORT=8801
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}/api/health"
PID_FILE="samaritan.pid"

# ── Kill existing instance ────────────────────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping PID $OLD_PID..."
    kill "$OLD_PID"
    for i in $(seq 1 10); do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.5
    done
  fi
  rm -f "$PID_FILE"
fi

# Fallback: kill by port in case PID file was stale
fuser -k ${HTTP_PORT}/tcp 8800/tcp 2>/dev/null || true

# Wait for port to actually free (up to 3s)
for i in $(seq 1 6); do
  fuser ${HTTP_PORT}/tcp 2>/dev/null || break
  sleep 0.5
done

# ── Start server ──────────────────────────────────────────────────────────────
source venv/bin/activate

# Process substitution keeps $! = python PID (not the awk subshell PID)
PYTHONUNBUFFERED=1 python -u samaritan.py \
  > >(stdbuf -oL awk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0; fflush() }' >> samaritan.log) \
  2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

# ── Health check ─────────────────────────────────────────────────────────────
echo "Waiting for server on :${HTTP_PORT}..."
for i in $(seq 1 20); do
  if curl -s --max-time 1 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
    echo "Started PID $PID — logging to samaritan.log"
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: server did not respond on ${HEALTH_URL} after 10s" >&2
exit 1
