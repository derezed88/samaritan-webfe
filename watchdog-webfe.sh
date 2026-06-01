#!/usr/bin/env bash
# watchdog-webfe.sh - health watchdog for Samaritan WebFE (voice frontend, port 8801)
#
# Problem this solves: start-pinggy.sh babysits the TUNNEL but assumes the
# backend stays up on its own. When samaritan.py dies, the tunnel keeps
# pointing at a dead port - the link looks connected but serves nothing.
# This watchdog health-checks the backend and restarts it via run.sh when
# it stops responding, so a silent crash self-heals.
#
# Usage:
#   ./watchdog-webfe.sh         # start in background (idempotent)
#   ./stop-watchdog-webfe.sh    # stop (or: kill $(cat watchdog-webfe.pid))
#   tail -f watchdog-webfe.log  # watch
#
# It restarts ONLY the backend. The pinggy tunnel self-recovers on its own
# once the backend answers again (its loop re-checks localhost:8801 every 15s),
# so no tunnel restart is needed here.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/watchdog-webfe.pid"
LOG_FILE="$SCRIPT_DIR/watchdog-webfe.log"
HTTP_PORT=8801
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}/api/health"
CHECK_INTERVAL=15        # seconds between health checks when healthy
FAIL_THRESHOLD=2         # consecutive failed checks before a restart
RESTART_COOLDOWN=20      # base seconds to wait after a restart attempt

# ── Single-instance guard ─────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "WebFE watchdog already running (PID $OLD_PID). Nothing to do."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# ── Fork to background ────────────────────────────────────────────────────
if [ -z "${WATCHDOG_DAEMON:-}" ]; then
    WATCHDOG_DAEMON=1 nohup "$0" >> "$LOG_FILE" 2>&1 &
    echo "WebFE watchdog started in background (PID $!)"
    echo "  Logs: tail -f $LOG_FILE"
    echo "  Stop: ./stop-watchdog-webfe.sh"
    exit 0
fi

# ── Daemon body ───────────────────────────────────────────────────────────
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"; exit 0' EXIT INT TERM
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "WebFE watchdog starting (PID $$) - checking $HEALTH_URL every ${CHECK_INTERVAL}s, restart after ${FAIL_THRESHOLD} consecutive failures"

consecutive_fails=0
restart_count=0

while true; do
    # Any real HTTP response (200, 401, etc) means the server is alive.
    # Empty or "000" means connection refused / no listener = down.
    CODE=$(curl -s --max-time 4 -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || true)

    if [ -n "$CODE" ] && [ "$CODE" != "000" ]; then
        if [ "$consecutive_fails" -ne 0 ]; then
            log "Backend healthy again (HTTP $CODE)."
        fi
        consecutive_fails=0
        restart_count=0
        sleep "$CHECK_INTERVAL"
        continue
    fi

    consecutive_fails=$((consecutive_fails + 1))
    log "Health check failed (code='${CODE:-none}') - consecutive ${consecutive_fails}/${FAIL_THRESHOLD}"

    if [ "$consecutive_fails" -ge "$FAIL_THRESHOLD" ]; then
        restart_count=$((restart_count + 1))
        log "Backend down - restart attempt #${restart_count} via run.sh"
        if ( cd "$SCRIPT_DIR" && ./run.sh ) >> "$LOG_FILE" 2>&1; then
            log "run.sh reported success."
        else
            log "run.sh reported FAILURE (nonzero exit) - will recheck and retry."
        fi
        consecutive_fails=0

        # Escalating backoff so a crash-looping backend is not hammered.
        if   [ "$restart_count" -ge 5 ]; then cooldown=120
        elif [ "$restart_count" -ge 3 ]; then cooldown=60
        else                                  cooldown=$RESTART_COOLDOWN
        fi
        log "Cooldown ${cooldown}s before resuming checks (restart_count=${restart_count})."
        sleep "$cooldown"
        continue
    fi

    sleep "$CHECK_INTERVAL"
done
