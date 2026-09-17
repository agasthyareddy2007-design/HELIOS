#!/usr/bin/env bash
#
# HELIOS — START (production stack natively via .venv/Tailscale Funnel).
#
#   ./start_helios.sh            # from the HELIOS directory
#   /home/agasthya/HELIOS/start_helios.sh   # from anywhere
#
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P)"
cd "$SCRIPT_DIR"

c_reset="\033[0m"; c_amber="\033[38;5;179m"; c_ok="\033[32m"; c_err="\033[31m"; c_cyan="\033[36m"
say()  { printf "%b\n" "${c_amber}[helios]${c_reset} $*"; }
ok()   { printf "%b\n" "${c_amber}[helios]${c_reset} ${c_ok}$*${c_reset}"; }
warn() { printf "%b\n" "${c_amber}[helios]${c_reset} ${c_err}$*${c_reset}"; }

if [ ! -d ".venv" ] && [ ! -d "venv" ]; then
    warn "Virtual environment not found. Please setup .venv first."
    exit 1
fi

VENV_DIR=".venv"
[ -d "venv" ] && VENV_DIR="venv"

if [ ! -f ".env" ]; then
    say "Creating .env from .env.example (please edit it later securely)..."
    cp .env.example .env
fi

mkdir -p data/runtime

say "Starting HELIOS V2 native backend (FastAPI :8011)..."
nohup "$VENV_DIR/bin/python" -m backend.app.api.v1_app --port 8011 > data/runtime/backend.log 2>&1 &
echo $! > data/runtime/backend.pid

# Check if Tailscale Funnel is running
TS_HOST=$(tailscale status --json | grep -o '"DNSName": "[^"]*' | head -1 | cut -d'"' -f4 | sed 's/\.$//')

echo ""
ok "HELIOS backend started"
echo ""
say "Local API:"
say "  http://127.0.0.1:8011/v1/health"
echo ""

say "To start frontend, run:"
say "  cd frontend && npm run dev"
echo ""

if [ -n "$TS_HOST" ]; then
    say "Public API (Tailscale Funnel):"
    say "  ${c_cyan}https://${TS_HOST}${c_reset}"
else
    warn "Tailscale not found or not connected."
    say "Public API:"
    say "  (Not available)"
fi

echo ""
say "Authentication:"
say "  X-API-Key required"
echo ""
say "Stop backend cleanly:"
say "  ./stop_helios.sh"
echo ""
