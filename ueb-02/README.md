# Übung 2 - SIMT-Ausführungsmodell & GPU-Speicherbandbreite

Two PyOpenCL micro-benchmarks for Heterogeneous Computing (2026S):

- **Aufgabe 1** - compute-bound kernel; scaling over `n` and warp/wavefront divergence.
- **Aufgabe 2** - memory-bound streaming kernel; coalesced / strided / random-gather
  bandwidth and latency hiding via occupancy.

Runs on **Windows and Linux** with any AMD/NVIDIA/Intel OpenCL device, or on CPU via POCL.

## Setup

### Linux
A helper script installs the OpenCL runtime, Python deps (into `.venv`), and LaTeX:
```bash
sudo bash setup.sh
```
Or do it manually:
```bash
sudo apt-get install -y ocl-icd-opencl-dev pocl-opencl-icd ocl-icd-libopencl1 clinfo
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
clinfo -l   # confirm a device is visible
```
For an AMD integrated GPU, the mesa ICD (`mesa-opencl-icd`, env `RUSTICL_ENABLE=radeonsi`)
exposes it; POCL provides a CPU fallback.

### Windows
Install the AMD Adrenalin driver (provides OpenCL), then:
```powershell
python -m pip install -r requirements.txt
```

## Run
```bash
python -m gpubench info --device gpu          # device facts
python -m gpubench all --device gpu           # full GPU sweeps -> results/
python -m gpubench baseline                   # NumPy CPU baselines -> results/
python -m gpubench plots                      # figures -> report/essay/figures/
```
`--device` accepts `gpu`, `cpu`, or a numeric index; `--quick` runs small sweeps.
Use `--device cpu` to run the same kernels on a POCL CPU device when no GPU is present.

## Tests
```bash
python -m pytest -v   # device-bound tests skip automatically if no OpenCL device
```

## Layout
- `gpubench/` - Python package (device, runner, benchmarks, baselines, plots, CLI)
- `gpubench/kernels/*.cl` - the only non-Python source (OpenCL-C)
- `results/` - committed JSON; `plots` regenerates the figures from it without a GPU
- `report/essay/` - LaTeX report (German); numbers are inline literals, figures come from `results/`
