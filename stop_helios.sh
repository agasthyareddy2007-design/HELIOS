#!/usr/bin/env bash
#
# HELIOS — STOP (native Python backend)
#
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P)"
cd "$SCRIPT_DIR"

c_reset="\033[0m"; c_amber="\033[38;5;179m"; c_ok="\033[32m"; c_err="\033[31m"
say()  { printf "%b\n" "${c_amber}[helios]${c_reset} $*"; }
ok()   { printf "%b\n" "${c_amber}[helios]${c_reset} ${c_ok}$*${c_reset}"; }
warn() { printf "%b\n" "${c_amber}[helios]${c_reset} ${c_err}$*${c_reset}"; }

PID_FILE="data/runtime/backend.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        say "Stopping HELIOS V2 backend (PID: $PID)..."
        kill "$PID"
        for i in {1..10}; do
            if ! kill -0 "$PID" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        if kill -0 "$PID" 2>/dev/null; then
            say "Force-killing PID: $PID..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        ok "HELIOS backend stopped cleanly."
    else
        warn "Process $PID is not running."
        rm -f "$PID_FILE"
    fi
else
    # Fallback to pkill
    if pgrep -f "backend.app.api.v1_app" >/dev/null; then
        say "Stopping running HELIOS backend instances..."
        pkill -f "backend.app.api.v1_app" || true
        ok "Stopped."
    else
        say "HELIOS backend is not running."
    fi
fi
