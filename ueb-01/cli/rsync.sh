#!/usr/bin/env bash
set -euo pipefail

# Configuration + helpers (BOARD, REMOTE_DIR, LOCAL_DIR, SSH_OPTS, check_board).
# shellcheck source=cli/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

case "${1:-}" in
  push)
    check_board
    # Laptop -> Board. NO --delete (safe). Preview with: ./cli/rsync.sh push --dry-run
    rsync -av -e "ssh $SSH_OPTS" --exclude='.git' "${@:2}" "$LOCAL_DIR" "$BOARD:$REMOTE_DIR"
    ;;
  pull)
    check_board
    # Board -> Laptop. Pulls the app structure/changes from the board.
    rsync -av -e "ssh $SSH_OPTS" --exclude='.git' "${@:2}" "$BOARD:$REMOTE_DIR" "$LOCAL_DIR"
    ;;
  *)
    echo "Usage: $0 {push|pull} [extra rsync options, e.g. --dry-run]"
    exit 1
    ;;
esac
