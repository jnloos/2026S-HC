# Design: SIMT Execution & GPU Memory Bandwidth (Übungsblatt 2)

**Date:** 2026-06-30
**Course:** Heterogeneous Computing, Sommer 2026 — Übungsblatt 2
**Deadline:** 2026-07-12
**Location in repo:** `ueb-02/`

## Goal

Two GPU micro-benchmarks that make the SIMT execution model visible and contrast it
with a CPU, plus a written results report (LaTeX → PDF, German).

- **Task 1 (compute-bound):** A configurable, purely arithmetic kernel (one element per
  thread). Scale problem size `n` into the millions, measure throughput (GFLOP/s), show
  the scaling/warm-up curve, then introduce **warp divergence** and measure the
  performance drop. Explain why a warp serializes divergent paths while a CPU barely
  cares.
- **Task 2 (memory-bound):** A streaming kernel `b[i] = a[i] * c` with low arithmetic
  intensity. Compare three access patterns — coalesced (stride 1), strided (stride k),
  random gather. Measure effective bandwidth (GB/s) vs. device peak. Show **latency
  hiding via occupancy** by varying work-group size / resident wavefronts. Explain the
  GPU (massive parallelism) vs. CPU (cache hierarchy) latency strategies.

## Constraints

- **Python-first**; drop to a C-like kernel language only where unavoidable.
- **Cross-platform: Windows AND Linux.**
- **Hardware:** AMD only — discrete AMD GPU on Windows, AMD integrated graphics on Linux.
  No NVIDIA, so no CUDA/CuPy/Numba; ROCm/HIP is not cross-platform for this hardware.
- Report must be reproducible from committed data on a machine without a GPU.
- Report carries the author's name (per user); other personal data (Matrikelnummer)
  stays redacted. Report language: **German**, aligned to the `ueb-01` essay style.

## Chosen Approach: PyOpenCL

PyOpenCL — Python host code, OpenCL-C kernels compiled at runtime by the driver. Reasons:

- Genuine AMD support on Windows (Adrenalin OpenCL) and Linux (mesa/rusticl ICD, or POCL).
- Maps onto the task vocabulary: warp → **wavefront** (queryable via
  `CL_KERNEL_PREFERRED_WORK_GROUP_SIZE_MULTIPLE`, 32/64 on AMD), block → **work-group**,
  occupancy → active wavefronts / max per CU.
- Most Python-first cross-platform option; runtime kernel compile captures the
  "drop to a kernel only where needed" philosophy without gcc.
- **The same OpenCL kernels run on a CPU device via POCL** → free empirical CPU baseline
  and GPU-free CI testability.

Rejected: wgpu-py (hides wavefronts/occupancy, weak timing), native C++ via the existing
`Importer.py` (not Python-first, Linux-only `.so`/gcc).

The existing `cs.c` / `cs.cpp` / `cs.py` / `lib/Importer.py` are unrelated (CPU
context-switch demo, Linux-only). They are **left untouched and not built upon**.

## Architecture

```
ueb-02/
  gpubench/
    __init__.py
    device.py        # platform/device selection (--device gpu|cpu|idx, PYOPENCL_CTX),
                     # device-info query, wavefront size, peak-bandwidth probe
    runner.py        # OpenCL program build + event-profiled timing
                     # (warm-up runs + median of N repeats; perf_counter fallback)
    kernels/
      compute.cl     # Task 1: per-element arithmetic load + configurable divergence
      memory.cl      # Task 2: b[i]=a[i]*c with 3 access patterns
    bench_compute.py # Task 1 sweeps (n scaling, divergence degree)
    bench_memory.py  # Task 2 sweeps (3 patterns, occupancy via work-group size)
    cpu_baseline.py  # NumPy + POCL CPU-device baselines
    plots.py         # matplotlib -> report/essay/figures/*.png from results JSON
    cli.py           # python -m gpubench {compute,memory,baseline,all,plots} ...
  results/           # raw JSON results, committed for reproducibility
  report/
    essay/report.tex # German, ueb-01 style, name kept
    essay/references.bib
    essay/figures/*.png
  README.md
  requirements.txt   # pyopencl, numpy, matplotlib
```

### Components & responsibilities

- **device.py** — picks an OpenCL context from a `--device` selector or `PYOPENCL_CTX`;
  exposes a `DeviceInfo` (name, type, compute units, max work-group size, wavefront width,
  global mem size, max clock, local mem). Provides a peak-bandwidth probe (large copy/
  triad) used as the reference for Task 2. One job: device discovery + facts.
- **runner.py** — builds a `cl.Program`, runs a kernel with profiling events enabled,
  applies warm-up + median-of-N, returns elapsed seconds + derived metrics. No knowledge
  of which benchmark it serves.
- **kernels/*.cl** — the only non-Python source. Parametrized via build `-D` defines and
  kernel args (load `k`, divergence degree `d`, stride `k`, pattern selector).
- **bench_*.py** — own the sweep definitions and metric math (FLOP counts, byte counts),
  emit JSON to `results/`.
- **cpu_baseline.py** — NumPy baselines (`a*c`, `a[perm]*c`, branchy vs. branchless) and
  optionally the same kernels on a POCL CPU device; same JSON schema.
- **plots.py** — pure function from `results/*.json` to figures; regenerable without a GPU.
- **cli.py** — thin entry point wiring the above; `--quick` for fast smoke runs.

## Task 1 detail — SIMT & warp divergence

- **Kernel:** one work-item per element; `k` iterations of an FMA/Horner loop on a
  register value; exactly 1 global read + 1 global write. FLOPs counted exactly
  (`flops_per_iter * k * n`) → GFLOP/s.
- **Scaling sweep:** `n` from ~1e3 to ~1e8 (capped by device memory). Plot GFLOP/s vs n;
  identify warm-up region and saturation point; relate the saturating thread count to
  `compute_units * max_wavefronts_per_cu * wavefront_width`.
- **Divergence:** `switch(lane % d)` (lane = `get_local_id(0)`), each of `d` branches an
  equal-cost loop, so a wavefront serializes `d` paths. Sweep `d` = 1 (none) … wavefront
  width (full). Plot throughput vs `d`; expect ≈ 1/d falloff until full divergence.
- **CPU baseline:** the same kernel on a POCL CPU device — divergence barely dents it
  (branch prediction + narrow SIMD). Headline GPU-vs-CPU contrast.

## Task 2 detail — bandwidth & latency hiding

- **Kernel:** `b[i] = a[i] * c`, index mode chosen by a parameter:
  1. coalesced: `idx = gid`
  2. strided: `idx = (gid * STRIDE) % n`
  3. random gather: `idx = perm[gid]` (fixed-seed permutation buffer)
- **Effective bandwidth:** `bytes_moved / time`; bytes = (read a + write b)·n·4 (+ index
  read for gather). Compare to measured peak-copy bandwidth and cite the card's spec in
  prose.
- **Latency hiding / occupancy:** sweep work-group size; throughput rises as more
  resident wavefronts hide memory stalls, then plateaus. Report occupancy as an
  **estimate** (wavefronts/group vs. max/CU), explicitly noting OpenCL exposes this less
  directly than CUDA's deviceQuery.
- **CPU baseline:** NumPy `a*c` (fast sequential) vs `a[perm]*c` (cache-miss slow) — the
  cache-vs-massive-parallelism contrast.

## Cross-platform, timing & reproducibility

- Device selection via `--device gpu|cpu|<index>` or `PYOPENCL_CTX`; non-interactive.
- Timing: OpenCL profiling events for kernel time, warm-up runs, median of N repeats,
  `time.perf_counter` wall-clock as fallback.
- Fixed RNG seed (`numpy.random.default_rng(SEED)`) for the gather permutation.
- All runs dump JSON to `results/`; `plots.py` and the report rebuild from that JSON, so
  figures regenerate on a GPU-less machine.
- README documents Linux ICD install (`mesa-opencl-icd`, `pocl-opencl-icd`, `clinfo`;
  rusticl via `RUSTICL_ENABLE=radeonsi`) vs. Windows (driver-provided).

## Testing

POCL CPU-device tests (no GPU needed, CI-friendly):
- compute kernel result matches the closed-form value for small `n`;
- memory kernel produces `b == a*c` for all three patterns;
- gather permutation is a valid bijection (covers every index once);
- `device.py` selects a context and reports a plausible wavefront width.

## Report

- LaTeX `article`, 12pt, `ngerman` babel, `biblatex` verbose-ibid — same preamble/style
  as `ueb-01/report/essay/report.tex`. Author name kept in header; no Matrikelnummer.
- Structure: Einführung → Methodik/Aufbau (PyOpenCL, Messmethodik) → Aufgabe 1 (SIMT &
  Warp-Divergenz, with scaling + divergence figures) → Aufgabe 2 (Bandbreite &
  Latenz-Hiding, with pattern + occupancy figures) → CPU-Vergleich → Fazit.
- Figures auto-generated by `plots.py` into `report/essay/figures/`.

## Out of scope

- NVIDIA/CUDA paths; ROCm/HIP.
- Multi-GPU.
- Touching or extending `Importer.py` / `cs.*`.
