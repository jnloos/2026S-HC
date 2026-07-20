# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ueb-02` is one assignment in the "Heterogeneous Computing" (2026S) course monorepo. It is a
self-contained PyOpenCL micro-benchmark suite (`gpubench`) plus a German LaTeX report, covering
two assignment parts:

- **Aufgabe 1** (compute-bound): throughput scaling over problem size `n`, and warp/wavefront
  divergence cost (`gpubench/kernels/compute.cl`, `bench_compute.py`).
- **Aufgabe 2** (memory-bound): streaming bandwidth for coalesced/strided/random-gather access
  patterns, and latency hiding via occupancy (`gpubench/kernels/memory.cl`, `bench_memory.py`).

## Environment

Use the project venv directly: `./.venv/bin/python -m gpubench ...` and `./.venv/bin/python -m pytest`.
On Linux, `sudo bash setup.sh` provisions the OpenCL ICD loader, AMD iGPU (mesa/rusticl) + POCL CPU
fallback, the venv, and the LaTeX toolchain. On a machine without a real GPU, only a **POCL CPU**
device is present — run everything with `--device cpu` (or `PYOPENCL_CTX`); the code is
device-agnostic so the same kernels run on CPU. The suite also runs on **Windows** (the AMD
Adrenalin driver supplies OpenCL): `python -m pip install -r requirements.txt`, then the same
`python -m gpubench ...` commands (no `setup.sh`, no venv path prefix).

## Commands

```bash
./.venv/bin/python -m gpubench info --device cpu       # device facts -> results/device_info.json
./.venv/bin/python -m gpubench all  --device cpu       # full sweeps  -> results/*.json
./.venv/bin/python -m gpubench baseline                # NumPy CPU baselines (no OpenCL device needed)
./.venv/bin/python -m gpubench plots                   # figures from results/ -> report/essay/figures/
./.venv/bin/python -m gpubench all --device gpu        # real-GPU sweep (run on a GPU host)

./.venv/bin/python -m pytest -q                        # full suite; device-bound tests auto-skip if no device
./.venv/bin/python -m pytest tests/test_memory.py::<name>   # single test

cd report/essay && latexmk -pdf report.tex             # build the German report PDF (biber-based)

./run_all.sh [gpu|cpu|<index>] [--quick]               # one-shot: sweeps + baselines + plots + PDF
```

`--quick` shrinks every sweep for a smoke run. `--device` accepts `gpu`, `cpu`, or a numeric device index.
`run_all.sh` chains the four steps end to end (device sweeps, baselines, `plots`, latexmk);
it is the intended way to refresh everything after new measurements.

## Architecture

The pipeline is **JSON-mediated and decoupled**, which is the key design fact:

1. Benchmark commands produce `results/*.json` (`{device, rows}`). The GPU is only needed at this step.
2. `plots` reads that committed JSON and regenerates `report/essay/figures/*.png` with **no GPU required**.
3. The LaTeX report includes those figures and is otherwise self-contained: the cited numbers in the
   prose and summary table are **literal values written directly into `report.tex`**. There is no
   auto-generated macro file. When new measurements change a number, update the figures via `plots`
   and edit the affected literals in `report.tex` by hand.

So the figures rebuild on any machine from committed results, and a GPU host is only needed to refresh
`results/*.json`. (A former `gpubench values` step generated a `values.tex` macro file that the report
`\input`ed; it was removed in favor of inline literals.)

Module responsibilities inside `gpubench/`:

- `cli.py` — argparse dispatch; `_sweeps()` defines the quick vs. full sweep parameters; `_write()`
  serializes results. This is where a new benchmark gets wired into a subcommand.
- `device.py` — OpenCL device discovery/selection (`select_context`), `DeviceInfo` query, and the
  `wavefront_width` probe (PREFERRED_WORK_GROUP_SIZE_MULTIPLE) used to size wavefront-aware sweeps.
- `runner.py` — the single timing primitive: builds programs and times kernels via OpenCL profiling
  events, returning the **median** of warmup+repeats launches. All benchmarks time through this.
- `bench_compute.py` / `bench_memory.py` — build kernels with `-D` macros, run sweeps, return `rows`.
- `cpu_baseline.py` — NumPy mirrors of the same workloads for a CPU reference (no OpenCL).
- `plots.py` — matplotlib (`Agg` backend); one `plot_*` per result file.
- `kernels/*.cl` — the only non-Python source. `compute.cl` is parameterized at build time with
  `-D KITERS=<k> -D DEGREE=<d>`; `DEGREE` controls how many equal-cost paths a wavefront serializes
  while keeping per-item FLOP count constant.

## Conventions specific to this repo

- **Strided pattern requires a stride coprime to `n`.** `(i*stride) % n` is only a bijection when
  `gcd(stride, n) == 1`; otherwise it collapses onto fewer addresses. `mem_n` is a power of two, so
  the code uses a prime stride (521). `make_index` raises if this is violated — don't "fix" it by
  removing the check.
- **Determinism:** the package seed is `gpubench.SEED = 1234`; pass it through to any RNG so gather
  patterns and baselines stay reproducible.
- **No em-dashes or AI-slop comments** in code, labels, or report prose — plain ASCII hyphens and
  direct wording only. Comments explain non-obvious *why* (e.g. the coprime-stride rationale), not what.
- Tests are designed to **skip, not fail**, when no OpenCL device or `pyopencl` is present
  (`tests/conftest.py` provides the `cl_context` fixture).

## Mandatory code review

Per the user's global instructions, after writing/editing/refactoring any code here, invoke the
`clean-code-review` skill before considering the task done (skip only for trivial doc/config edits).
