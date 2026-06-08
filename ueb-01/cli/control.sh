#!/usr/bin/env bash
set -euo pipefail

# Remote control of the DigSig app on the UNO Q.
# Wrapper around `arduino-app-cli` over SSH.

# Configuration + helpers (BOARD, APP_ID, REMOTE_DIR, SSH_OPTS, check_board).
# shellcheck source=cli/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Small helpers: run a command on the board.
remote()     { ssh    $SSH_OPTS "$BOARD" "$@"; }
remote_tty() { ssh -t $SSH_OPTS "$BOARD" "$@"; }

# USB-C port role of the UNO Q. The single USB-C port is OTG/dual-role:
#   host   = board drives peripherals (camera) — persistent default via service.
#   device = board presents as a USB gadget to the laptop (needed for App Lab
#            over USB; "device" in DWC3/OTG terms, colloquially "client").
# Switched via the dwc3 debugfs mode file (the path verified in the fix, see
# report/notes/01-usb-host-camera-issue.md).
#
# NOT hardcoded: the controller (e.g. "4e00000.usb") is discovered on the board
# at runtime — there is exactly one dwc3 role switch. This keeps the script
# independent of the concrete SoC address. Overridable via env
# (USB_ROLE_FILE / USB_MODE_FILE empty => auto-discovery; USB_SERVICE = unit name).
USB_ROLE_FILE="${USB_ROLE_FILE:-}"
USB_MODE_FILE="${USB_MODE_FILE:-}"
USB_SERVICE="${USB_SERVICE:-uno-q-usb-host.service}"

# Shell prelude that sets ROLE_FILE/MODE_FILE on the board. Order: explicit env
# overrides > auto-discovery of the single dwc3 controller. Aborts with a clear
# message if no controller is found.
usb_prelude() {
  cat <<EOF
ROLE_FILE="${USB_ROLE_FILE}"
MODE_FILE="${USB_MODE_FILE}"
if [ -z "\$ROLE_FILE" ] || [ -z "\$MODE_FILE" ]; then
  rs=\$(ls -d /sys/class/usb_role/*-role-switch 2>/dev/null | head -1)
  [ -n "\$rs" ] || { echo "ERROR: no USB role switch found (no dwc3/OTG port?)." >&2; exit 1; }
  ctrl=\$(basename "\$rs" -role-switch)
  [ -z "\$ROLE_FILE" ] && ROLE_FILE="\$rs/role"
  [ -z "\$MODE_FILE" ] && MODE_FILE="/sys/kernel/debug/usb/\$ctrl/mode"
fi
EOF
}

cmd_status() {
  # Filters the header line + the DigSig app's line from `app list`.
  # awk instead of grep so the header always comes along.
  remote "arduino-app-cli app list" \
    | awk -v id="$APP_ID" 'NR==1 || $1==id'
}

cmd_logs() {
  # ${1:-} = optional extra flags (e.g. --tail 200, if the CLI supports them).
  remote "arduino-app-cli app logs '$APP_ID' ${1:-}"
}

cmd_follow() {
  # Live log stream. Stop with Ctrl-C.
  # -t allocates a TTY so Ctrl-C propagates cleanly to the CLI.
  remote_tty "arduino-app-cli app logs --follow '$APP_ID'"
}

cmd_start() { remote "arduino-app-cli app start '$APP_ID'"; }
cmd_stop()  { remote "arduino-app-cli app stop '$APP_ID'"; }

# Find the name of the main container (running main.py). `-a` so a stopped
# container is found too (docker restart then starts it).
main_container() { remote "docker ps -a --format '{{.Names}}' | grep -m1 -E 'digsig.*main'" 2>/dev/null; }

cmd_restart() {
  # IMPORTANT: `arduino-app-cli app stop/start` does NOT reload the Python app —
  # the container keeps running, main.py is not re-executed, so neither
  # runtime.env nor changed assets/ are re-read. Worse, `app start` then falsely
  # reports "App Is Running". The reliable path is restarting the main container
  # (re-exec of main.py).
  local cname
  cname="$(main_container)"
  if [ -n "$cname" ]; then
    echo "restart via docker: $cname" >&2
    remote "docker restart '$cname'"
  else
    echo "Main container not found — falling back to arduino-app-cli." >&2
    cmd_stop || true
    sleep 2
    cmd_start
  fi
}

cmd_shell() {
  # Convenient entry point for ad-hoc debugging right on the board.
  # $REMOTE_DIR contains a literal ~ that only the remote shell expands.
  remote_tty "cd $REMOTE_DIR && exec \$SHELL -l"
}

cmd_info() {
  # Static facts (always available, even when the board is offline).
  local host="${BOARD#*@}"
  echo "Board:    $BOARD"
  echo "App ID:   $APP_ID"
  echo "App dir:  $REMOTE_DIR"
  echo "SSH:      ssh $BOARD"
  echo "Sync:     ./cli/rsync.sh push"
  echo "Web UI:   http://$host:$WEB_UI_PORT"

  # Runtime info only if the board is reachable without a password
  # (BatchMode -> never a password prompt, don't trigger key setup).
  if ! ssh $SSH_OPTS -o BatchMode=yes -o ConnectTimeout=5 "$BOARD" 'true' 2>/dev/null; then
    echo
    echo "(Board offline or key auth not set up — no runtime info.)"
    return 0
  fi

  # Get the board's IP -> extra URL by IP (in case mDNS is flaky).
  local ip
  ip="$(remote 'hostname -I 2>/dev/null' | awk '{print $1}')"
  [ -n "$ip" ] && echo "Board IP: $ip" && echo "Web UI:   http://$ip:$WEB_UI_PORT (by IP)"

  echo
  echo "=== Status ==="
  cmd_status
}

cmd_report() {
  echo "=== Status ($APP_ID) ==="
  cmd_status
  echo
  echo "=== Recent logs ==="
  cmd_logs
}

cmd_usb_status() {
  # Current role + service state. The role is readable without root; the debugfs
  # mode file needs root, so we deliberately read only the role here. No -t
  # needed (no sudo) — avoids the "Pseudo-terminal" warning.
  remote "$(usb_prelude)
    echo \"role:    \$(cat \"\$ROLE_FILE\" 2>/dev/null || echo '?')  (\$ROLE_FILE)\"
    echo \"service: \$(systemctl is-enabled $USB_SERVICE 2>/dev/null || true) / \$(systemctl is-active $USB_SERVICE 2>/dev/null || true)\"
    echo 'lsusb:'
    lsusb 2>/dev/null | sed 's/^/  /'
  "
}

cmd_usb_host() {
  # Camera/peripheral mode: board is USB host. The service keeps this across
  # reboots; the explicit echo takes effect immediately (start is a no-op for an
  # already-active oneshot and wouldn't re-run ExecStart otherwise).
  echo "-> USB-C: HOST mode (camera/peripheral) ..." >&2
  remote_tty "$(usb_prelude)
    sudo systemctl start $USB_SERVICE
    echo host | sudo tee \"\$MODE_FILE\" >/dev/null && echo OK"
  cmd_usb_status
}

cmd_usb_device() {
  # App Lab / laptop mode: board is USB device (gadget). Stop the service, else
  # it immediately forces host again. A reboot restores host (the service stays
  # enabled) — for permanent device: 'sudo systemctl disable $USB_SERVICE'.
  echo "-> USB-C: DEVICE mode (App Lab / laptop) ..." >&2
  echo "   (stops camera access until you switch back to host)" >&2
  remote_tty "$(usb_prelude)
    sudo systemctl stop $USB_SERVICE
    echo device | sudo tee \"\$MODE_FILE\" >/dev/null && echo OK"
  echo "Note: a reboot restores HOST. Permanent device -> 'sudo systemctl disable $USB_SERVICE'." >&2
  cmd_usb_status
}

# --- pipeline configuration (delegates to configure.sh) ---------------------
# Apply runtime settings to the deployed app: configure.sh writes runtime.env,
# syncs it and restarts the app. We pass through the board's CURRENT CMS_URL
# (from the local runtime.env) so flipping a pipeline knob doesn't re-point the
# board at a freshly-detected laptop IP — only the requested keys change.
cmd_config() {
  if [[ $# -eq 0 || "$1" == "--show" || "$1" == "show" ]]; then
    "$CLI_DIR/configure.sh" --show
    return
  fi
  local envf="$REPO_ROOT/arduino/python/runtime.env" cms=""
  [[ -f "$envf" ]] && cms="$(grep -E '^CMS_URL=' "$envf" | tail -1 | cut -d= -f2-)"
  if [[ -n "$cms" ]]; then
    "$CLI_DIR/configure.sh" "CMS_URL=$cms" "$@"
  else
    "$CLI_DIR/configure.sh" "$@"
  fi
}

# Friendly shortcuts. v3 / face / person all need the camera, so enable it too.
cmd_variant() {
  case "${1:-}" in
    v1|edge)   cmd_config SELECTOR_MODE=edge ;;
    v2|hybrid) cmd_config SELECTOR_MODE=hybrid ;;
    v3|cloud)  cmd_config SELECTOR_MODE=cloud ENABLE_CAMERA=true ;;
    *) echo "Usage: $0 variant <v1|v2|v3>   (edge | hybrid | cloud)" >&2; exit 1 ;;
  esac
}
cmd_audience() {
  case "${1:-}" in
    static) cmd_config AUDIENCE_MODE=static ;;
    face)   cmd_config AUDIENCE_MODE=face ENABLE_CAMERA=true ;;
    *) echo "Usage: $0 audience <static|face>" >&2; exit 1 ;;
  esac
}
cmd_trigger() {
  case "${1:-}" in
    timer)  cmd_config TRIGGER_MODE=timer ;;
    person) cmd_config TRIGGER_MODE=person ENABLE_CAMERA=true ;;
    *) echo "Usage: $0 trigger <timer|person>" >&2; exit 1 ;;
  esac
}

usage() {
  cat >&2 <<EOF
Usage: $0 <command>

App control:
  start            start the app
  stop             stop the app
  restart          stop + start (defensive, in case 'app restart' is missing)

Diagnostics:
  info             URL (Web UI), board IP, SSH/sync commands + status
  report           status + recent logs (default)
  status           only the 'arduino-app-cli app list' line for $APP_ID
  logs [flags]     print logs (extra flags are passed through, e.g. --tail 200)
  follow           stream logs live (Ctrl-C to stop)

Pipeline settings (write runtime.env, sync + restart; CMS_URL preserved):
  variant <v1|v2|v3>     switch SELECTOR_MODE (edge | hybrid | cloud)
  audience <static|face> switch AUDIENCE_MODE (face also enables the camera)
  trigger <timer|person> switch TRIGGER_MODE
  config KEY=VALUE ...    set any runtime key(s), e.g. config TIMER_INTERVAL_SEC=20
  config --show          print the active runtime.env

USB-C port role (single port is OTG/dual-role):
  usb-host         host mode: board drives peripherals (camera). Default.
  usb-device       device mode: board as USB gadget to the laptop (App Lab over USB).
  usb-client       alias for usb-device
  usb-status       current role + service state + lsusb

Other:
  shell            open an SSH shell in the app directory on the board

Configuration: BOARD=${BOARD:-<unset>}  APP_ID=$APP_ID
EOF
}

case "${1:-report}" in
  info)           require_board; cmd_info ;;
  report)         check_board; cmd_report ;;
  status)         check_board; cmd_status ;;
  logs)           check_board; cmd_logs "${2:-}" ;;
  follow|tail)    check_board; cmd_follow ;;
  start)          check_board; cmd_start ;;
  stop)           check_board; cmd_stop ;;
  restart)        check_board; cmd_restart ;;
  shell)          check_board; cmd_shell ;;
  variant)        cmd_variant "${2:-}" ;;
  audience)       cmd_audience "${2:-}" ;;
  trigger)        cmd_trigger "${2:-}" ;;
  config|set)     shift; cmd_config "$@" ;;
  usb-host)            check_board; cmd_usb_host ;;
  usb-device|usb-client) check_board; cmd_usb_device ;;
  usb-status)          check_board; cmd_usb_status ;;
  -h|--help|help) usage ;;
  *)              usage; exit 1 ;;
esac
