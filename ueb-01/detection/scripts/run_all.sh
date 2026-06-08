#!/usr/bin/env bash
# Run the full audience-classifier pipeline end to end.
#
# Steps: fetch_models -> download_data -> prepare -> train -> export_onnx
#        -> make_fixtures -> sanity_infer
#
# Pass-through args (e.g. --subset 8000, --max-train 20000, --epochs 12) are
# forwarded ONLY to the stages that accept them. Example:
#
#   bash scripts/run_all.sh --subset 8000 --epochs 12
#
# Set RUN_ALL_DRYRUN=1 to print the per-stage commands (with forwarded args)
# without executing anything — used to verify arg forwarding.
set -euo pipefail

# Resolve detection root relative to this script (scripts/ -> parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PY="$ROOT_DIR/.venv/bin/python"
DRYRUN="${RUN_ALL_DRYRUN:-0}"

if [[ "$DRYRUN" != 1 && ! -x "$PY" ]]; then
  echo "ERROR: venv python not found at $PY (create it: uv venv --python 3.12 $ROOT_DIR/.venv)" >&2
  exit 1
fi

# All pass-through args.
PASS_ARGS=("$@")

# Print only the flags (and their values) a given stage understands.
# Usage: filter_args "--flag-a --flag-b" "${PASS_ARGS[@]}"
filter_args() {
  local accepted=" $1 "; shift
  local out=() a
  while (( $# )); do
    a="$1"
    if [[ "$accepted" == *" $a "* ]]; then
      out+=("$a")
      # Take the following token as the value unless it's another flag.
      if [[ -n "${2:-}" && "${2:-}" != --* ]]; then out+=("$2"); shift; fi
    fi
    shift
  done
  (( ${#out[@]} )) && printf '%s\n' "${out[@]}"
}

run_step() {
  echo ""
  echo "=============================================================="
  echo ">> $*"
  echo "=============================================================="
  [[ "$DRYRUN" == 1 ]] && return 0
  "$@"
}

cd "$SCRIPT_DIR"

# --- 1. fetch YuNet (no pass-through args) ---
run_step "$PY" fetch_models.py

# --- 2. download FairFace (accepts --subset) ---
mapfile -t DL_ARGS < <(filter_args "--subset" "${PASS_ARGS[@]}")
run_step "$PY" download_data.py "${DL_ARGS[@]}"

# --- 3. prepare crops (accepts --subset, --score-threshold, --expand) ---
mapfile -t PREP_ARGS < <(filter_args "--subset --score-threshold --expand" "${PASS_ARGS[@]}")
run_step "$PY" prepare.py "${PREP_ARGS[@]}"

# --- 4. train (accepts --max-train, --epochs, --batch-size, --lr, ...) ---
mapfile -t TRAIN_ARGS < <(filter_args "--max-train --epochs --batch-size --lr --input-size --val-frac --freeze-epochs --num-workers" "${PASS_ARGS[@]}")
run_step "$PY" train.py "${TRAIN_ARGS[@]}"

# --- 5. export ONNX + labels.json + model card (accepts --int8, --opset, --input-size) ---
mapfile -t EXP_ARGS < <(filter_args "--int8 --opset --input-size" "${PASS_ARGS[@]}")
run_step "$PY" export_onnx.py "${EXP_ARGS[@]}"

# --- 6. make fixtures (no pass-through args) ---
run_step "$PY" make_fixtures.py

# --- 7. sanity inference ---
run_step "$PY" sanity_infer.py

echo ""
echo "All steps complete. Artifacts in $ROOT_DIR/models and $ROOT_DIR/artifacts."
