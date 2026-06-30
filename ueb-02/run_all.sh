#!/usr/bin/env bash
#
# run_all.sh - run all benchmarks + baselines, regenerate the figures, and
# rebuild the report PDF, in one shot.
#
# Usage:
#   ./run_all.sh [device] [--quick]
#     device   gpu (default) | cpu | <numeric index>
#     --quick  small sweeps for a fast smoke run
#
# Examples:
#   ./run_all.sh                # full sweeps on the GPU, rebuild report
#   ./run_all.sh cpu            # full sweeps on the POCL CPU device
#   ./run_all.sh gpu --quick    # quick GPU smoke run
#
set -euo pipefail

# Always operate from the project root (this script's directory).
cd "$(dirname "${BASH_SOURCE[0]}")"

# Parse args: a bare token is the device, --quick toggles small sweeps.
DEVICE="gpu"
QUICK=""
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK="--quick" ;;
        -h|--help) sed -n '3,16p' "$0"; exit 0 ;;
        *) DEVICE="$arg" ;;
    esac
done

# Use the project venv if it exists, otherwise fall back to system python.
if [[ -x .venv/bin/python ]]; then
    PY=".venv/bin/python"
else
    PY="python3"
fi

echo "==> $($PY --version) | device=${DEVICE} ${QUICK:+(quick)}"

echo "==> [1/5] Device sweeps (Aufgabe 1 + 2) -> results/"
$PY -m gpubench all --device "${DEVICE}" ${QUICK}

echo "==> [2/5] CPU baselines (NumPy) -> results/"
$PY -m gpubench baseline ${QUICK}

echo "==> [3/5] Figures from results JSON -> report/essay/figures/"
$PY -m gpubench plots

echo "==> [4/5] Report values (numbers + device flags) -> report/essay/values.tex"
$PY -m gpubench values

echo "==> [5/5] Rebuild report PDF -> report/essay/report.pdf"
if command -v latexmk >/dev/null 2>&1; then
    ( cd report/essay && latexmk -pdf -interaction=nonstopmode -halt-on-error report.tex >/dev/null )
    ( cd report/essay && latexmk -c >/dev/null 2>&1 || true )   # tidy aux files, keep the PDF
else
    # Fallback without latexmk: explicit pdflatex + bibtex passes.
    ( cd report/essay \
        && pdflatex -interaction=nonstopmode -halt-on-error report.tex >/dev/null \
        && bibtex report >/dev/null \
        && pdflatex -interaction=nonstopmode -halt-on-error report.tex >/dev/null \
        && pdflatex -interaction=nonstopmode -halt-on-error report.tex >/dev/null )
fi

echo "==> Done. Updated results/*.json, report/essay/figures/*.png, report/essay/report.pdf"
