#!/usr/bin/env bash
# Shared configuration + helpers for the board CLI scripts.
# Sourced by rsync.sh, control.sh, configure.sh, dev.sh and verify-pipelines.sh.

# This script's directory (= cli/) and the repo root — independent of the CWD.
CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$CLI_DIR")"

# Load local configuration (cli/.env) if present. `set -a` exports the
# assignments, `set +a` turns that off again.
if [[ -f "$CLI_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$CLI_DIR/.env"
  set +a
fi

# --- Configuration (override in cli/.env; copy cli/env.xmpl) -----------------
# BOARD has no built-in default on purpose — it is machine-specific (the board's
# SSH target, user@host). Set it in cli/.env. require_board() enforces this with
# a clear message before any board operation.
BOARD="${BOARD:-}"
APP_ID="${APP_ID:-user:digsig-prototype}"
REMOTE_DIR="${REMOTE_DIR:-~/ArduinoApps/digsig-prototype/}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
# Port on which the web_ui brick serves assets/ (see arduino/app.yaml).
WEB_UI_PORT="${WEB_UI_PORT:-7000}"
# Only the Arduino app is synced to the board (not the api/ project).
LOCAL_DIR="${LOCAL_DIR:-$REPO_ROOT/arduino/}"

# Save the host key automatically on first connect (no interactive prompt), but
# still reject a later change (MITM protection).
SSH_OPTS="-o StrictHostKeyChecking=accept-new"

# Source IP of the default route = the LAN IP the board uses to reach us. Shared
# here so dev.sh and configure.sh don't each define their own copy.
detect_ip() { ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1; }

# Fail fast with a helpful message if BOARD isn't configured.
require_board() {
  if [[ -z "$BOARD" ]]; then
    echo "ERROR: BOARD is not set. Copy cli/env.xmpl to cli/.env and set BOARD=user@host." >&2
    echo "       e.g. BOARD=arduino@uno-q.local" >&2
    exit 1
  fi
}

# Ensure password-less login works and the board is reachable.
# - Generates an SSH key once (no passphrase, so it's scriptable).
# - Installs the public key on the board the first time (one password prompt).
# - After that, every command runs without a password prompt.
check_board() {
  require_board
  if [[ ! -f "$SSH_KEY" ]]; then
    echo "No SSH key found — generating $SSH_KEY ..." >&2
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -q -C "$(whoami)@$(hostname)"
  fi

  # Does password-less login already work? (BatchMode -> never ask for a password)
  if ssh $SSH_OPTS -o BatchMode=yes -o ConnectTimeout=5 "$BOARD" 'true' 2>/dev/null; then
    return 0
  fi

  # No -> copy the key to the board. Fails if the board is unreachable.
  echo "Setting up password-less login — please enter the board password ONCE." >&2
  if ! ssh-copy-id $SSH_OPTS -o ConnectTimeout=5 -i "$SSH_KEY.pub" "$BOARD"; then
    echo "ERROR: key setup failed. Is the board ($BOARD) reachable? Password correct?" >&2
    exit 1
  fi
}
