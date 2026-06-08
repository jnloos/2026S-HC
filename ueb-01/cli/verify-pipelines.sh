#!/usr/bin/env bash
# Fully-automatic end-to-end verification of all three variant pipelines.
#
#   Part A (off-board, deterministic): boots a local CMS API and runs the
#     pipeline-variant harness — proves V1/V2/V3 (and face->V2) each complete a
#     full cycle against the real API/Claude, with the board bricks mocked and
#     audience inference running in-process. This gates the exit code.
#   Part B (on-board, best-effort): if the board is reachable, cycles the real
#     board app through each variant (timer trigger), polling the app log for a
#     completed cycle. Failures here are reported, not fatal (Part A already
#     proves the wiring; on-board needs Caddy/camera/LLM).
#
# Usage:  ./cli/verify-pipelines.sh            # both parts
#         SKIP_ONBOARD=1 ./cli/verify-pipelines.sh   # off-board only
#
# The face->V2 row needs cv2 + onnxruntime in the runner's Python (and the ONNX
# models); it SKIPs cleanly otherwise. Set VERIFY_PYTHON to a venv that has them
# to exercise it (e.g. VERIFY_PYTHON=detection/.venv/bin/python).
#
# No arguments, no interaction required.
set -uo pipefail

# shellcheck source=cli/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

API_PORT="${API_PORT:-8000}"
API_URL="http://127.0.0.1:${API_PORT}"
API_DIR="$REPO_ROOT/api"
VERIFY_PYTHON="${VERIFY_PYTHON:-python3}"
RUN="${TMPDIR:-/tmp}/digsig-verify"
mkdir -p "$RUN"

# Track which services THIS script started, so we only tear those down.
STARTED_API=0

log()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }

board_reachable() { timeout 8 ssh $SSH_OPTS -o BatchMode=yes -o ConnectTimeout=6 "$BOARD" true 2>/dev/null; }

wait_http() {  # url, label, tries
  local url="$1" label="$2" tries="${3:-30}" i=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    i=$((i+1)); [[ $i -ge $tries ]] && { echo "ERROR: $label not reachable ($url)" >&2; return 1; }
    sleep 1
  done
  info "$label up ($url)"
}

start_local_api() {
  if curl -fsS "$API_URL/openapi.json" >/dev/null 2>&1; then info "API already running"; return 0; fi
  [[ -x "$API_DIR/.venv/bin/uvicorn" ]] || { echo "ERROR: api/.venv missing" >&2; return 1; }
  ( cd "$API_DIR" && .venv/bin/digsig db upgrade >/dev/null 2>&1 || true )
  ( cd "$API_DIR" && nohup .venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port "$API_PORT" \
      >"$RUN/api.log" 2>&1 & echo $! >"$RUN/api.pid" )
  STARTED_API=1
  wait_http "$API_URL/openapi.json" "API"
}

ensure_seed() {
  local n; n="$(curl -fsS "$API_URL/pools/1" 2>/dev/null | grep -o '"id"' | wc -l)"
  if [[ "${n:-0}" -lt 2 ]]; then
    info "seeding bakery fixture ..."
    ( cd "$API_DIR" && .venv/bin/digsig seed bakery >/dev/null 2>&1 || true )
  fi
}

cleanup() {
  [[ "$STARTED_API" == 1 && -f "$RUN/api.pid" ]] && kill "$(cat "$RUN/api.pid")" 2>/dev/null
  rm -f "$RUN/api.pid"
}
trap cleanup EXIT

# Result matrix: name -> off / on
declare -A OFF ON
OFF=([v1]="?" [v2]="?" [v3]="?" [face]="?")
ON=([v1]="-" [v2]="-" [v3]="-")

# ---------------------------------------------------------------- Part A ------
log "Part A — off-board pipeline harness"
start_local_api  || { echo "API could not start" >&2; exit 1; }
ensure_seed

PYTEST_OUT="$RUN/partA.txt"
# -o addopts= clears the project pytest.ini's "-q" so -v actually prints
# per-test "PASSED/SKIPPED" lines that the matrix parsing below reads.
( cd "$REPO_ROOT/arduino/python" && CMS_URL="$API_URL" \
    "$VERIFY_PYTHON" -m pytest tests/test_pipeline_variants.py -o addopts= -p no:randomly -v ) >"$PYTEST_OUT" 2>&1
PARTA_RC=$?
verdict() { # test-substring -> PASS/FAIL/SKIP
  grep -E "$1" "$PYTEST_OUT" | grep -qE "PASSED" && { echo PASS; return; }
  grep -E "$1" "$PYTEST_OUT" | grep -qE "SKIPPED" && { echo SKIP; return; }
  echo FAIL
}
OFF[v1]=$(verdict "test_v1_edge_pipeline")
OFF[v2]=$(verdict "test_v2_hybrid_pipeline")
OFF[v3]=$(verdict "test_v3_cloud_pipeline")
OFF[face]=$(verdict "test_face_audience_steers")
sed -n '$p' "$PYTEST_OUT" | sed 's/^/   pytest: /'

# ---------------------------------------------------------------- Part B ------
if [[ "${SKIP_ONBOARD:-0}" == 1 ]]; then
  log "Part B — skipped (SKIP_ONBOARD=1)"
elif ! board_reachable; then
  log "Part B — skipped (board $BOARD not reachable)"
else
  log "Part B — on-board (best-effort)"
  info "wiring board -> laptop API (dev.sh up) ..."
  "$CLI_DIR/dev.sh" up >"$RUN/devup.log" 2>&1 && info "dev.sh up OK" || info "dev.sh up had issues (see $RUN/devup.log)"

  # Drive one variant on-board and wait for a completed pipeline cycle in the log.
  onboard_variant() { # key, selector_mode, expected_vtag, audience_mode, enable_camera, timeout_s
    local key="$1" sel="$2" vtag="$3" aud="$4" cam="$5" to="$6"
    info "variant $key: SELECTOR_MODE=$sel AUDIENCE_MODE=$aud ENABLE_CAMERA=$cam (timeout ${to}s)"
    "$CLI_DIR/configure.sh" SELECTOR_MODE="$sel" TRIGGER_MODE=timer AUDIENCE_MODE="$aud" \
        ENABLE_CAMERA="$cam" TIMER_INTERVAL_SEC=20 >>"$RUN/onboard-$key.log" 2>&1
    local waited=0
    while (( waited < to )); do
      if "$CLI_DIR/control.sh" logs --tail 80 2>/dev/null | grep -q "PIPELINE_CYCLE_OK.*variant=$vtag"; then
        ON[$key]="PASS"; info "variant $key: cycle OK ($vtag)"; return 0
      fi
      sleep 5; waited=$((waited+5))
    done
    ON[$key]="FAIL"; info "variant $key: no completed cycle within ${to}s"
    return 1
  }
  onboard_variant v2 hybrid v2 static false 70  || true   # fastest / most deterministic
  onboard_variant v1 edge   v1 static false 200 || true   # on-device LLM is slow
  onboard_variant v3 cloud  v3 static true  100 || true   # needs the camera
fi

# ----------------------------------------------------------------- matrix -----
log "RESULT MATRIX"
printf '   %-8s %-10s %-10s\n' "variant" "off-board" "on-board"
printf '   %-8s %-10s %-10s\n' "V1 edge"   "${OFF[v1]}"   "${ON[v1]}"
printf '   %-8s %-10s %-10s\n' "V2 hybrid" "${OFF[v2]}"   "${ON[v2]}"
printf '   %-8s %-10s %-10s\n' "V3 cloud"  "${OFF[v3]}"   "${ON[v3]}"
printf '   %-8s %-10s %-10s\n' "face->V2"  "${OFF[face]}" "-"
echo
if [[ "$PARTA_RC" -eq 0 ]]; then
  echo "OFF-BOARD: all pipelines running ✓"
  exit 0
else
  echo "OFF-BOARD: FAILURES (see $PYTEST_OUT)"
  exit 1
fi
