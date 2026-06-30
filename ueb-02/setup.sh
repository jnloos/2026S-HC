#!/usr/bin/env bash
#
# setup.sh — provision the toolchain for ueb-02 (SIMT & GPU bandwidth benchmarks).
#
# Installs (Debian/Ubuntu, AMD target):
#   - OpenCL ICD loader + AMD iGPU (mesa/rusticl) + CPU (POCL) devices + clinfo
#   - Python venv tooling (python3-venv, python3-pip)
#   - LaTeX for building the report PDF
# Then creates ./.venv (owned by your user, not root) and installs the Python deps.
#
# Usage:
#   sudo bash setup.sh
#
set -euo pipefail

# --- must run as root (for apt), but we want the venv owned by the real user -------------
if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: run this with sudo, e.g.  sudo bash setup.sh" >&2
    exit 1
fi

# The unprivileged user who invoked sudo (falls back to root if run as root directly).
REAL_USER="${SUDO_USER:-root}"
REAL_HOME="$(getent passwd "${REAL_USER}" | cut -d: -f6)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Repo:        ${REPO_DIR}"
echo "==> Venv owner:  ${REAL_USER}"
echo

# --- 1. system packages ------------------------------------------------------------------
echo "==> [1/4] Installing system packages (OpenCL, Python, LaTeX)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y

apt-get install -y --no-install-recommends \
    `# OpenCL: ICD loader, dev headers, inspector` \
    ocl-icd-libopencl1 ocl-icd-opencl-dev clinfo \
    `# OpenCL devices: AMD integrated GPU (mesa/rusticl) + CPU fallback (POCL)` \
    mesa-opencl-icd pocl-opencl-icd \
    `# Python virtual-env + pip` \
    python3-venv python3-pip python3-dev \
    `# build tools (pyopencl may compile its C extension)` \
    build-essential \
    `# LaTeX toolchain for the report` \
    texlive-latex-recommended texlive-latex-extra texlive-lang-german \
    texlive-bibtex-extra biber latexmk

# --- 2. verify an OpenCL device is visible ----------------------------------------------
echo
echo "==> [2/4] Probing OpenCL devices (clinfo -l)..."
if clinfo -l 2>/dev/null | grep -qiE 'platform|device'; then
    clinfo -l || true
else
    echo "WARNING: clinfo found no OpenCL platform/device." >&2
    echo "         The AMD iGPU may need rusticl. Try re-running benchmarks with:" >&2
    echo "             export RUSTICL_ENABLE=radeonsi" >&2
    echo "         POCL should still expose a CPU device for the baseline/tests." >&2
fi

# --- 3. python venv + deps (as the real user, so it is NOT root-owned) --------------------
echo
echo "==> [3/4] Creating ./.venv and installing Python deps as '${REAL_USER}'..."
sudo -u "${REAL_USER}" -H bash -euo pipefail <<EOF
cd "${REPO_DIR}"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pyopencl numpy matplotlib pytest
EOF

# --- 4. done -----------------------------------------------------------------------------
echo
echo "==> [4/4] Setup complete."
cat <<EOF

Next steps (run as ${REAL_USER}, no sudo needed):

    cd "${REPO_DIR}"
    source .venv/bin/activate

    pytest -q                                  # run the test suite
    python -m gpubench all      --device gpu    # Task 1 + 2 GPU sweeps  -> results/*.json
    python -m gpubench baseline                 # NumPy + POCL CPU baselines
    python -m gpubench plots                    # results -> report/essay/figures/*.png
    cd report/essay && latexmk -pdf report.tex  # build the report PDF

If the AMD iGPU is not listed by 'clinfo -l', prefix runs with:
    export RUSTICL_ENABLE=radeonsi
EOF
