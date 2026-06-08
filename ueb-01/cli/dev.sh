#!/usr/bin/env bash
set -euo pipefail
# "Dev mode" — brings up all parts of the DigSig app for development:
#   1. local API (FastAPI/uvicorn) on 0.0.0.0:PORT  (the board must reach us)
#   2. runtime.env with the auto-detected laptop IP  ->  board CMS_URL
#   3. sync the Arduino app to the board + restart it
#
# Usage:
#   ./cli/dev.sh up        # bring everything up (default)
#   ./cli/dev.sh down      # stop the local API
#   ./cli/dev.sh status    # state (API / IP / board app)
#   ./cli/dev.sh ip        # print the detected LAN IP
#   ./cli/dev.sh logs      # follow the local API log
#   ./cli/dev.sh restart   # restart the API + reconfigure the board
#
# Env: API_PORT (default 8000).

# shellcheck source=cli/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

API_DIR="$REPO_ROOT/api"
VENV="$API_DIR/.venv"
# uvicorn runs internally + unprivileged; Caddy (port 80) fronts it externally
# under /digsig. So bind to localhost only — 8000 is not exposed on the LAN.
PORT="${API_PORT:-8000}"
HOST="${API_HOST:-127.0.0.1}"
CMS_PATH="${CMS_PATH:-/digsig}"   # Caddy path through which the board reaches the API
RUN_DIR="$REPO_ROOT/.dev"
PIDFILE="$RUN_DIR/api.pid"
LOGFILE="$RUN_DIR/api.log"

# detect_ip() comes from _common.sh.
api_running()  { [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

start_api() {
  mkdir -p "$RUN_DIR"
  if api_running; then echo "API already running (PID $(cat "$PIDFILE"), port $PORT)."; return 0; fi
  [[ -x "$VENV/bin/uvicorn" ]] || {
    echo "ERROR: $VENV missing. Set it up first:" >&2
    echo "  cd api && python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
  }
  # Clean up orphaned uvicorn instances (e.g. after an unclean stop), otherwise
  # the port stays bound ("address already in use").
  pkill -f "uvicorn app.api.main:app" 2>/dev/null && sleep 1 || true
  echo "-> applying DB migrations ..."
  ( cd "$API_DIR" && "$VENV/bin/digsig" db upgrade >/dev/null 2>&1 || true )
  echo "-> uvicorn on $HOST:$PORT  (log: $LOGFILE)"
  # `python -m uvicorn` so $! is exactly the uvicorn process (clean PID handling).
  ( cd "$API_DIR" && nohup "$VENV/bin/python" -m uvicorn app.api.main:app --host "$HOST" --port "$PORT" \
      >"$LOGFILE" 2>&1 & echo $! > "$PIDFILE" )
  sleep 2
  if api_running; then
    echo "API started (PID $(cat "$PIDFILE"))."
  else
    echo "ERROR: API failed to start — last log lines:" >&2; tail -n 20 "$LOGFILE" >&2; exit 1
  fi
}

stop_api() {
  local killed=0
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null && killed=1
  fi
  # Backstop: also clean up orphaned instances not recorded in the PID file.
  pkill -f "uvicorn app.api.main:app" 2>/dev/null && killed=1 || true
  rm -f "$PIDFILE"
  [[ $killed -eq 1 ]] && echo "API stopped." || echo "API was not running."
}

bring_up() {
  local ip; ip="$(detect_ip)"
  [[ -z "$ip" ]] && { echo "ERROR: LAN IP not detected." >&2; exit 1; }
  echo "== Dev mode up =="
  echo "Laptop IP: $ip   uvicorn: $HOST:$PORT (internal)   Board -> Caddy: http://$ip$CMS_PATH"
  start_api
  echo "-> configuring board (CMS_URL=http://$ip$CMS_PATH via Caddy) ..."
  "$CLI_DIR/configure.sh" --ip "$ip"
  # Quick reachability check via Caddy (the way the board sees the API).
  local code
  code="$(python3 -c "import urllib.request as u; print(u.urlopen('http://$ip$CMS_PATH/pools/1', timeout=5).status)" 2>/dev/null || echo ERR)"
  echo "   Caddy check http://$ip$CMS_PATH/pools/1 -> $code"
  echo
  echo "Ready:"
  echo "  API internal:  http://$HOST:$PORT      (Docs: /docs  ·  Debug UI: /debug)"
  echo "  Board->API:    http://$ip$CMS_PATH     (via Caddy)"
  echo "  Board UI:      http://${BOARD#*@}:$WEB_UI_PORT"
  echo "  Logs:          ./cli/dev.sh logs   ·   Board: ./cli/control.sh follow"
}

case "${1:-up}" in
  up)      bring_up ;;
  down)    stop_api ;;
  restart) stop_api; bring_up ;;
  status)
    api_running && echo "API:   running (PID $(cat "$PIDFILE"), port $PORT)" || echo "API:   stopped"
    echo "IP:    $(detect_ip)"
    if check_board >/dev/null 2>&1; then "$CLI_DIR/control.sh" status; else echo "Board: not reachable"; fi
    ;;
  ip)      detect_ip ;;
  logs)    [[ -f "$LOGFILE" ]] && tail -n 50 -f "$LOGFILE" || { echo "No API log ($LOGFILE) — is the API running?"; exit 1; } ;;
  -h|--help) sed -n '2,20p' "$0" ;;
  *)       echo "Usage: $0 {up|down|restart|status|ip|logs}"; exit 1 ;;
esac
