#!/bin/bash
# HappyCapy Slack Skill - Launch Script
#
# Usage:
#   bash start.sh              - Start in foreground (default, good for debugging)
#   bash start.sh daemon       - Start as background daemon (24/7 auto-restart)
#   bash start.sh stop         - Stop the running daemon
#   bash start.sh restart      - Restart the daemon
#   bash start.sh status       - Show daemon status

set -e

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE_PY="$SKILL_DIR/scripts/bridge.py"
DATA_DIR="$HOME/.happycapy-slack"
PID_FILE="$DATA_DIR/daemon.pid"
LOG_FILE="$DATA_DIR/bridge.log"

# Ensure data directory exists
mkdir -p "$DATA_DIR"

CMD="${1:-foreground}"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

stop_daemon() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "Stopping HappyCapy Slack daemon (PID $PID)..."
        kill "$PID" 2>/dev/null || true
        # Wait up to 10s for clean exit
        for i in $(seq 1 10); do
            sleep 1
            if ! kill -0 "$PID" 2>/dev/null; then
                echo "Daemon stopped."
                rm -f "$PID_FILE"
                return 0
            fi
        done
        echo "Daemon did not stop cleanly — sending SIGKILL."
        kill -9 "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
    else
        echo "Daemon is not running."
        rm -f "$PID_FILE" 2>/dev/null || true
    fi
}

start_daemon() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "Daemon is already running (PID $PID). Use 'restart' to restart."
        return 0
    fi

    echo "Starting HappyCapy Slack daemon (24/7 auto-restart)..."

    # Use pm2 if available, otherwise nohup supervisor loop
    if command -v pm2 &>/dev/null; then
        pm2 start "$BRIDGE_PY" \
            --name "happycapy-slack" \
            --interpreter python3 \
            --output "$LOG_FILE" \
            --error "$LOG_FILE" \
            --restart-delay 3000 \
            --max-restarts 50 2>/dev/null || true
        # pm2 manages its own PID; write approximate marker
        pm2 pid happycapy-slack 2>/dev/null | head -1 > "$PID_FILE" 2>/dev/null || true
        echo "Started with pm2. Use 'pm2 logs happycapy-slack' to view logs."
    else
        # nohup supervisor: restarts on crash with exponential backoff
        (
            BACKOFF=3
            MAX_BACKOFF=120
            RESTARTS=0
            MAX_RESTARTS=50
            STABILITY=300

            while [ $RESTARTS -lt $MAX_RESTARTS ]; do
                START_TS=$(date +%s)
                python3 "$BRIDGE_PY" >> "$LOG_FILE" 2>&1
                EXIT_CODE=$?
                END_TS=$(date +%s)
                RUN_SECS=$((END_TS - START_TS))

                # Reset counter if process was stable
                if [ $RUN_SECS -ge $STABILITY ]; then
                    RESTARTS=0
                    BACKOFF=3
                fi

                RESTARTS=$((RESTARTS + 1))
                echo "$(date '+%Y-%m-%d %H:%M:%S') [DAEMON] Bridge exited (code $EXIT_CODE, ran ${RUN_SECS}s). Restart $RESTARTS/$MAX_RESTARTS in ${BACKOFF}s..." >> "$LOG_FILE"
                sleep $BACKOFF
                BACKOFF=$(( BACKOFF * 2 ))
                [ $BACKOFF -gt $MAX_BACKOFF ] && BACKOFF=$MAX_BACKOFF
            done

            echo "$(date '+%Y-%m-%d %H:%M:%S') [DAEMON] Max restarts ($MAX_RESTARTS) reached. Giving up." >> "$LOG_FILE"
            rm -f "$PID_FILE"
        ) &

        DAEMON_PID=$!
        echo $DAEMON_PID > "$PID_FILE"
        echo "Started daemon (PID $DAEMON_PID)."
        echo "Logs: tail -f $LOG_FILE"
    fi
}

# ---------------------------------------------------------------------------
# main dispatch
# ---------------------------------------------------------------------------

case "$CMD" in
    daemon|start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        stop_daemon
        sleep 2
        start_daemon
        ;;
    status)
        if is_running; then
            PID=$(cat "$PID_FILE")
            echo "HappyCapy Slack daemon is RUNNING (PID $PID)."
            echo "Logs: $LOG_FILE"
            if [ -f "$LOG_FILE" ]; then
                echo ""
                echo "--- Last 10 log lines ---"
                tail -10 "$LOG_FILE"
            fi
        else
            echo "HappyCapy Slack daemon is NOT running."
        fi
        ;;
    foreground|"")
        echo "Starting HappyCapy Slack bridge in foreground..."
        exec python3 "$BRIDGE_PY"
        ;;
    *)
        echo "Usage: $0 {foreground|daemon|start|stop|restart|status}"
        exit 1
        ;;
esac
