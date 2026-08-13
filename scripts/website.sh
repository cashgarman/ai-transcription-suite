#!/usr/bin/env bash
# Manages the Summit marketing website in website/ on a local machine.
# Usage: scripts/website.sh <command> [port]
#
#   install   Install npm dependencies.
#   dev       Run the dev server in the foreground with hot reload.
#   serve     Run the dev server in the background and return.
#   build     Produce a production build.
#   start     Build if needed, then run the production server in the background.
#   stop      Stop whichever server this script started.
#   restart   Stop, rebuild, then start the production server again.
#   status    Report whether a server is running and on which port.
#   logs      Print the background server log (add -f to follow).
#   open      Open the running site in the default browser.
#   lint      Run eslint.
#   check     Run the TypeScript compiler with no emit.
#   clean     Remove .next, the log, and the pid file.
#   reset     clean, plus remove node_modules.

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
SITE_DIR="$PROJECT_DIR/website"
PID_FILE="$SITE_DIR/.website-server.pid"
LOG_FILE="$SITE_DIR/.website-server.log"
BUILD_DIR="$SITE_DIR/.next"

COMMAND=${1:-status}
PORT=${2:-3100}
HOST=${HOST:-0.0.0.0}

step()    { printf '  \033[36m%s\033[0m\n' "$1"; }
note()    { printf '  \033[90m%s\033[0m\n' "$1"; }
good()    { printf '  \033[32m%s\033[0m\n' "$1"; }
problem() { printf '  \033[33m%s\033[0m\n' "$1"; }

if [ ! -d "$SITE_DIR" ]; then
    echo "No website directory at $SITE_DIR." >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo 'npm was not found on PATH. Install Node.js 20 or newer.' >&2
    exit 1
fi

install_if_needed() {
    if [ ! -d "$SITE_DIR/node_modules" ]; then
        step 'Installing dependencies (first run).'
        (cd "$SITE_DIR" && npm install)
    fi
}

tracked_pid() {
    [ -f "$PID_FILE" ] || return 1
    local recorded
    recorded=$(tr -d '[:space:]' < "$PID_FILE")
    if [ -z "$recorded" ] || ! kill -0 "$recorded" 2>/dev/null; then
        rm -f "$PID_FILE"
        return 1
    fi
    printf '%s' "$recorded"
}

port_busy() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1
    elif command -v ss >/dev/null 2>&1; then
        ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN
    else
        return 1
    fi
}

lan_urls() {
    good "Ready at http://127.0.0.1:$PORT"
    if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
        if command -v hostname >/dev/null 2>&1; then
            hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' | grep -v '^127\.' | while read -r ip; do
                good "LAN    http://${ip}:$PORT"
            done
        fi
    fi
}

wait_for_port() {
    local waited=0
    while [ "$waited" -lt 60 ]; do
        if port_busy; then
            lan_urls
            return 0
        fi
        if ! tracked_pid >/dev/null; then
            problem 'The server exited during startup. Recent output:'
            tail -n 40 "$LOG_FILE" 2>/dev/null || true
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    problem "Port $PORT did not open within 60 seconds. Check: scripts/website.sh logs"
}

start_background() {
    local script=$1
    if tracked_pid >/dev/null; then
        problem "A server is already running (pid $(tracked_pid)). Stop it first."
        return 0
    fi
    if port_busy; then
        problem "Port $PORT is already in use."
        return 0
    fi

    rm -f "$LOG_FILE"
    (cd "$SITE_DIR" && nohup npm run "$script" -- --hostname "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE")

    step "Started '$script' in the background (pid $(cat "$PID_FILE"))."
    wait_for_port
}

stop_server() {
    if ! tracked_pid >/dev/null; then
        note 'No tracked server is running.'
        return 0
    fi
    local target
    target=$(tracked_pid)
    step "Stopping pid $target and its children."
    pkill -TERM -P "$target" 2>/dev/null || true
    kill -TERM "$target" 2>/dev/null || true
    sleep 1
    kill -KILL "$target" 2>/dev/null || true
    rm -f "$PID_FILE"
    good 'Stopped.'
}

case "$COMMAND" in
    install)
        step 'Installing dependencies.'
        (cd "$SITE_DIR" && npm install)
        ;;
    dev)
        install_if_needed
        step "Dev server on $HOST:$PORT (Ctrl+C to stop)."
        lan_urls
        (cd "$SITE_DIR" && npm run dev -- --hostname "$HOST" --port "$PORT")
        ;;
    serve)
        install_if_needed
        start_background dev
        ;;
    build)
        install_if_needed
        step 'Building for production.'
        (cd "$SITE_DIR" && npm run build)
        ;;
    start)
        install_if_needed
        if [ ! -d "$BUILD_DIR" ]; then
            step 'No build found; building first.'
            (cd "$SITE_DIR" && npm run build)
        fi
        start_background start
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        install_if_needed
        (cd "$SITE_DIR" && npm run build)
        start_background start
        ;;
    status)
        if tracked_pid >/dev/null; then
            good "Tracked server: running (pid $(tracked_pid))."
        else
            note 'Tracked server: not running.'
        fi
        if port_busy; then
            good "Port $PORT: listening"
            lan_urls
        else
            note "Port $PORT: free."
        fi
        if [ -d "$SITE_DIR/node_modules" ]; then
            note 'Dependencies: installed.'
        else
            problem 'Dependencies: missing. Run: scripts/website.sh install'
        fi
        if [ -d "$BUILD_DIR" ]; then
            note 'Production build: present.'
        else
            note 'Production build: none.'
        fi
        ;;
    logs)
        if [ ! -f "$LOG_FILE" ]; then
            note 'No log yet.'
        elif [ "${2:-}" = "-f" ] || [ "${3:-}" = "-f" ]; then
            tail -f "$LOG_FILE"
        else
            tail -n 40 "$LOG_FILE"
        fi
        ;;
    open)
        if ! port_busy; then
            problem "Nothing is listening on port $PORT. Start it with: scripts/website.sh serve"
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://localhost:$PORT" >/dev/null 2>&1 &
        elif command -v open >/dev/null 2>&1; then
            open "http://localhost:$PORT"
        else
            note "Open http://localhost:$PORT in a browser."
        fi
        ;;
    lint)
        install_if_needed
        (cd "$SITE_DIR" && npm run lint)
        ;;
    check)
        install_if_needed
        (cd "$SITE_DIR" && npx tsc --noEmit) && good 'No type errors.'
        ;;
    clean)
        stop_server
        rm -rf "$BUILD_DIR" "$LOG_FILE" "$PID_FILE"
        note 'Removed build output, log, and pid file.'
        ;;
    reset)
        stop_server
        rm -rf "$BUILD_DIR" "$LOG_FILE" "$PID_FILE" "$SITE_DIR/node_modules"
        note 'Removed build output, log, pid file, and node_modules.'
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        sed -n '2,20p' "$0" >&2
        exit 1
        ;;
esac
