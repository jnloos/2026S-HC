# GPU SIMT & Bandwidth Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two cross-platform PyOpenCL micro-benchmarks (compute-bound with warp divergence; memory-bound with three access patterns) plus CPU baselines, auto-generated plots, and a German LaTeX report, for Heterogeneous Computing Übungsblatt 2.

**Architecture:** A small Python package `gpubench` under `ueb-02/`. Python orchestrates; the only non-Python source is two OpenCL-C kernels compiled at runtime. A `device` layer discovers/queries an OpenCL device (GPU or POCL CPU), a `runner` layer times kernels with profiling events, and `bench_*` modules own the sweeps and metric math, dumping JSON to `results/`. `plots.py` rebuilds figures from that JSON so the report regenerates without a GPU.

**Tech Stack:** Python 3.12, PyOpenCL, NumPy, matplotlib, pytest; OpenCL via AMD driver (Windows) or POCL/mesa ICD (Linux); LaTeX (`article`, `ngerman` babel, `biblatex`).

## Global Constraints

- Python-first; the only C-like source is OpenCL-C kernels (`gpubench/kernels/*.cl`). One line each below, taken from the spec:
- Must run on **Windows AND Linux**; no NVIDIA/CUDA, no ROCm/HIP.
- Device selection via `--device gpu|cpu|<index>` or `PYOPENCL_CTX`; never interactive.
- All benchmarks dump JSON to `ueb-02/results/`; `plots.py` rebuilds figures from JSON only (GPU-less reproducibility).
- Fixed RNG seed `SEED = 1234` (`numpy.random.default_rng(SEED)`) wherever randomness appears.
- Tests must skip gracefully (not fail) when no OpenCL platform/device is present.
- Do not modify or build upon `cs.c`, `cs.cpp`, `cs.py`, `lib/Importer.py`.
- Report: German, LaTeX, same preamble/style as `ueb-01/report/essay/report.tex`; author name kept; no Matrikelnummer.
- All paths below are relative to `ueb-02/`. Commit after every task.

---

### Task 1: Project scaffolding & OpenCL environment

**Files:**
- Create: `requirements.txt`
- Create: `gpubench/__init__.py`
- Create: `gpubench/kernels/__init__.py`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_environment.py`
- Create: `results/.gitkeep`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/conftest.py` fixture `cl_context` (a `pyopencl.Context` or `pytest.skip`), used by every later test; `gpubench` importable package.

- [x] **Step 1: Install OpenCL runtime + Python deps**

On Linux (this dev box is Ubuntu):
```bash
sudo apt-get update
sudo apt-get install -y ocl-icd-opencl-dev pocl-opencl-icd ocl-icd-libopencl1 clinfo
```
On Windows the AMD Adrenalin driver already provides OpenCL; skip the apt step.

Then (any OS):
```bash
cd ueb-02
python -m pip install -r requirements.txt   # after Step 2 writes the file
```

- [x] **Step 2: Write `requirements.txt`**

```
pyopencl>=2024.1
numpy>=1.26
matplotlib>=3.8
pytest>=8.0
```

- [x] **Step 3: Write package init files**

`gpubench/__init__.py`:
```python
"""GPU SIMT & bandwidth micro-benchmarks (PyOpenCL)."""

__all__ = ["device", "runner", "bench_compute", "bench_memory", "cpu_baseline", "plots"]

SEED = 1234
```
`gpubench/kernels/__init__.py`:
```python
"""OpenCL-C kernel sources for the benchmarks."""
```
`tests/__init__.py`: empty file.

- [x] **Step 4: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -ra
```

- [x] **Step 5: Write `tests/conftest.py`**

```python
import pytest

try:
    import pyopencl as cl
except Exception:  # pragma: no cover - import guard
    cl = None


def _first_device():
    if cl is None:
        return None
    try:
        for platform in cl.get_platforms():
            devs = platform.get_devices()
            if devs:
                return devs[0]
    except Exception:
        return None
    return None


@pytest.fixture(scope="session")
def cl_context():
    """A pyopencl.Context on any available device, or skip if none."""
    if cl is None:
        pytest.skip("pyopencl not installed")
    dev = _first_device()
    if dev is None:
        pytest.skip("no OpenCL device available")
    return cl.Context([dev])
```

- [x] **Step 6: Write `tests/test_environment.py`**

```python
def test_gpubench_imports():
    import gpubench
    assert gpubench.SEED == 1234


def test_pyopencl_importable():
    import pyopencl as cl
    assert hasattr(cl, "get_platforms")


def test_context_or_skip(cl_context):
    # If a device exists, the fixture yields a usable context.
    assert cl_context is not None
```

- [x] **Step 7: Create `results/.gitkeep`** (empty file, so the dir is tracked).

- [x] **Step 8: Run tests**

Run: `cd ueb-02 && python -m pytest -v`
Expected: PASS (or `test_context_or_skip` SKIPPED if no device on this box; the other two PASS).

- [x] **Step 9: Commit**

```bash
git add ueb-02/requirements.txt ueb-02/gpubench ueb-02/tests ueb-02/pytest.ini ueb-02/results/.gitkeep
git commit -m "Scaffold gpubench package and OpenCL test harness"
```

---

### Task 2: Device discovery & info (`device.py`)

**Files:**
- Create: `gpubench/device.py`
- Create: `tests/test_device.py`

**Interfaces:**
- Consumes: `cl_context` fixture.
- Produces:
  - `@dataclass DeviceInfo(name:str, dtype:str, compute_units:int, max_work_group_size:int, wavefront:int, global_mem_bytes:int, max_clock_mhz:int, local_mem_bytes:int)`
  - `select_context(selector: str | None = None) -> cl.Context` — `selector` in `{"gpu","cpu",<int-as-str>,None}`; `None` prefers a GPU else first device; honors `PYOPENCL_CTX`.
  - `query_device_info(ctx: cl.Context) -> DeviceInfo`
  - `wavefront_width(ctx: cl.Context) -> int`
  - `peak_bandwidth_gbps(ctx: cl.Context, nbytes: int = 256*1024*1024) -> float`

- [x] **Step 1: Write failing test `tests/test_device.py`**

```python
import pytest
from gpubench import device


def test_query_device_info(cl_context):
    info = device.query_device_info(cl_context)
    assert info.name
    assert info.compute_units >= 1
    assert info.max_work_group_size >= 1
    assert info.global_mem_bytes > 0


def test_wavefront_width_is_power_of_two(cl_context):
    w = device.wavefront_width(cl_context)
    assert w >= 1
    assert (w & (w - 1)) == 0  # power of two (1,8,16,32,64...)


def test_peak_bandwidth_positive(cl_context):
    bw = device.peak_bandwidth_gbps(cl_context, nbytes=8 * 1024 * 1024)
    assert bw > 0
```

- [x] **Step 2: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_device.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'gpubench.device'`) — or SKIP if no device.

- [x] **Step 3: Implement `gpubench/device.py`**

```python
"""OpenCL device discovery, info query, and a peak-bandwidth probe."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np
import pyopencl as cl


@dataclass
class DeviceInfo:
    name: str
    dtype: str
    compute_units: int
    max_work_group_size: int
    wavefront: int
    global_mem_bytes: int
    max_clock_mhz: int
    local_mem_bytes: int


def _all_devices():
    out = []
    for platform in cl.get_platforms():
        for dev in platform.get_devices():
            out.append(dev)
    return out


def select_context(selector: str | None = None) -> cl.Context:
    """Pick a context. selector: 'gpu' | 'cpu' | '<index>' | None.

    None prefers a GPU, else the first device. PYOPENCL_CTX is honored when
    selector is None.
    """
    if selector is None and os.environ.get("PYOPENCL_CTX"):
        return cl.create_some_context(interactive=False)

    devices = _all_devices()
    if not devices:
        raise RuntimeError("no OpenCL devices available")

    if selector in (None, "gpu"):
        gpus = [d for d in devices if d.type & cl.device_type.GPU]
        if gpus:
            return cl.Context([gpus[0]])
        if selector == "gpu":
            raise RuntimeError("no GPU device available")
        return cl.Context([devices[0]])
    if selector == "cpu":
        cpus = [d for d in devices if d.type & cl.device_type.CPU]
        if not cpus:
            raise RuntimeError("no CPU device available")
        return cl.Context([cpus[0]])
    # numeric index
    idx = int(selector)
    return cl.Context([devices[idx]])


def _type_name(dev) -> str:
    if dev.type & cl.device_type.GPU:
        return "GPU"
    if dev.type & cl.device_type.CPU:
        return "CPU"
    return "OTHER"


def query_device_info(ctx: cl.Context) -> DeviceInfo:
    dev = ctx.devices[0]
    return DeviceInfo(
        name=dev.name.strip(),
        dtype=_type_name(dev),
        compute_units=dev.max_compute_units,
        max_work_group_size=dev.max_work_group_size,
        wavefront=wavefront_width(ctx),
        global_mem_bytes=dev.global_mem_size,
        max_clock_mhz=dev.max_clock_frequency,
        local_mem_bytes=dev.local_mem_size,
    )


_PROBE_SRC = "__kernel void probe(__global float *a){ a[get_global_id(0)] *= 2.0f; }"


def wavefront_width(ctx: cl.Context) -> int:
    """Wavefront/warp width = preferred work-group-size multiple of a kernel."""
    dev = ctx.devices[0]
    prog = cl.Program(ctx, _PROBE_SRC).build()
    return prog.probe.get_work_group_info(
        cl.kernel_work_group_info.PREFERRED_WORK_GROUP_SIZE_MULTIPLE, dev
    )


def peak_bandwidth_gbps(ctx: cl.Context, nbytes: int = 256 * 1024 * 1024) -> float:
    """Measured copy bandwidth (read+write) as a peak reference for Task 2."""
    n = nbytes // 4
    queue = cl.CommandQueue(ctx, properties=cl.command_queue_properties.PROFILING_ENABLE)
    mf = cl.mem_flags
    a = cl.Buffer(ctx, mf.READ_ONLY, size=n * 4)
    b = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    host = np.ones(n, dtype=np.float32)
    cl.enqueue_copy(queue, a, host)
    prog = cl.Program(ctx, "__kernel void cpy(__global const float*a,__global float*b){"
                            "int i=get_global_id(0); b[i]=a[i];}").build()
    # warm-up
    prog.cpy(queue, (n,), None, a, b).wait()
    best = None
    for _ in range(5):
        ev = prog.cpy(queue, (n,), None, a, b)
        ev.wait()
        secs = (ev.profile.end - ev.profile.start) * 1e-9
        best = secs if best is None else min(best, secs)
    moved = 2 * n * 4  # read a + write b
    return (moved / best) / 1e9
```

- [x] **Step 4: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_device.py -v`
Expected: PASS (or SKIP without a device).

- [x] **Step 5: Commit**

```bash
git add ueb-02/gpubench/device.py ueb-02/tests/test_device.py
git commit -m "Add OpenCL device discovery, info query and peak-bandwidth probe"
```

---

### Task 3: Timing harness (`runner.py`)

**Files:**
- Create: `gpubench/runner.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- Consumes: `cl_context`.
- Produces:
  - `make_queue(ctx: cl.Context) -> cl.CommandQueue` (profiling enabled)
  - `build_program(ctx: cl.Context, src: str, options: str = "") -> cl.Program`
  - `time_event(events: list[cl.Event]) -> float` — median seconds from profiling events
  - `time_kernel(queue, callable_launch, *, warmup:int=2, repeats:int=7) -> float` where `callable_launch() -> cl.Event` enqueues one launch and returns its event; returns median seconds.

- [x] **Step 1: Write failing test `tests/test_runner.py`**

```python
import numpy as np
import pyopencl as cl
from gpubench import runner


def test_time_kernel_runs_and_is_positive(cl_context):
    ctx = cl_context
    queue = runner.make_queue(ctx)
    n = 1 << 16
    prog = runner.build_program(
        ctx, "__kernel void k(__global float*a){int i=get_global_id(0); a[i]+=1.0f;}"
    )
    a = cl.Buffer(ctx, cl.mem_flags.READ_WRITE, size=n * 4)
    cl.enqueue_copy(queue, a, np.zeros(n, np.float32))

    def launch():
        return prog.k(queue, (n,), None, a)

    secs = runner.time_kernel(queue, launch, warmup=1, repeats=3)
    assert secs > 0
```

- [x] **Step 2: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_runner.py -v`
Expected: FAIL (`No module named 'gpubench.runner'`) or SKIP.

- [x] **Step 3: Implement `gpubench/runner.py`**

```python
"""Build OpenCL programs and time kernels with profiling events."""
from __future__ import annotations

from statistics import median
from typing import Callable

import pyopencl as cl


def make_queue(ctx: cl.Context) -> cl.CommandQueue:
    return cl.CommandQueue(
        ctx, properties=cl.command_queue_properties.PROFILING_ENABLE
    )


def build_program(ctx: cl.Context, src: str, options: str = "") -> cl.Program:
    return cl.Program(ctx, src).build(options=options)


def _event_seconds(ev: cl.Event) -> float:
    ev.wait()
    return (ev.profile.end - ev.profile.start) * 1e-9


def time_kernel(
    queue: cl.CommandQueue,
    launch: Callable[[], cl.Event],
    *,
    warmup: int = 2,
    repeats: int = 7,
) -> float:
    """Run `launch` warmup+repeats times; return median kernel seconds."""
    for _ in range(warmup):
        _event_seconds(launch())
    samples = [_event_seconds(launch()) for _ in range(repeats)]
    return median(samples)
```

- [x] **Step 4: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_runner.py -v`
Expected: PASS (or SKIP).

- [x] **Step 5: Commit**

```bash
git add ueb-02/gpubench/runner.py ueb-02/tests/test_runner.py
git commit -m "Add profiled kernel timing harness"
```

---

### Task 4: Compute kernel & Task-1 benchmark (`compute.cl`, `bench_compute.py`)

**Files:**
- Create: `gpubench/kernels/compute.cl`
- Create: `gpubench/bench_compute.py`
- Create: `tests/test_compute.py`

**Interfaces:**
- Consumes: `device`, `runner`.
- Produces:
  - `FLOPS_PER_ITER = 2`
  - `reference_value(x0: float, k: int) -> float` — closed-form host mirror of the kernel's per-element math (for correctness tests).
  - `load_source() -> str`
  - `run_scaling(ctx, ns: list[int], k: int) -> list[dict]` → dicts `{n,k,seconds,gflops}`
  - `run_divergence(ctx, n: int, k: int, degrees: list[int]) -> list[dict]` → `{n,k,degree,seconds,gflops}`

**Kernel math:** each work-item starts from `x = 1.0 + gid*1e-7` and runs `k` FMA steps `x = x*COEF + BIAS` (2 FLOPs each). Divergent variant: `switch(get_local_id(0) % degree)` with `degree` branches, each doing the same `k`-step FMA loop, so a wavefront serializes `degree` paths.

- [x] **Step 1: Write `gpubench/kernels/compute.cl`**

```c
// Configurable arithmetic load, one work-item per element.
// Build-time: -D KITERS=<k> -D DEGREE=<d>
#ifndef KITERS
#define KITERS 256
#endif
#ifndef DEGREE
#define DEGREE 1
#endif

#define COEF 0.9999997f
#define BIAS 0.0000013f

inline float work(float x) {
    for (int i = 0; i < KITERS; ++i) {
        x = x * COEF + BIAS;   // 2 FLOPs
    }
    return x;
}

__kernel void compute_uniform(__global float *out, const int n) {
    int gid = get_global_id(0);
    if (gid >= n) return;
    float x = 1.0f + gid * 1e-7f;
    out[gid] = work(x);
}

__kernel void compute_divergent(__global float *out, const int n) {
    int gid = get_global_id(0);
    if (gid >= n) return;
    float x = 1.0f + gid * 1e-7f;
    int lane = get_local_id(0) % DEGREE;
    // Each branch does identical work; divergence forces serialization.
    switch (lane) {
        case 0: x = work(x); break;
        case 1: x = work(x); break;
        case 2: x = work(x); break;
        case 3: x = work(x); break;
        case 4: x = work(x); break;
        case 5: x = work(x); break;
        case 6: x = work(x); break;
        case 7: x = work(x); break;
        default: {
            // lanes >= 8 fan out further by their own id
            for (int s = 0; s < lane; ++s) x = work(x) * 1.0f;
            break;
        }
    }
    out[gid] = x;
}
```

- [x] **Step 2: Write failing test `tests/test_compute.py`**

```python
import numpy as np
import pyopencl as cl
from gpubench import bench_compute, runner


def test_reference_value_matches_kernel(cl_context):
    ctx = cl_context
    queue = runner.make_queue(ctx)
    n = 1024
    k = 64
    prog = runner.build_program(ctx, bench_compute.load_source(), options=f"-D KITERS={k} -D DEGREE=1")
    out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)
    prog.compute_uniform(queue, (n,), None, out, np.int32(n)).wait()
    host = np.empty(n, np.float32)
    cl.enqueue_copy(queue, host, out).wait()
    expected = bench_compute.reference_value(1.0 + 0 * 1e-7, k)
    assert abs(host[0] - expected) < 1e-3


def test_run_scaling_reports_gflops(cl_context):
    rows = bench_compute.run_scaling(cl_context, ns=[1 << 12, 1 << 14], k=128)
    assert len(rows) == 2
    assert all(r["gflops"] > 0 for r in rows)


def test_run_divergence_degrades(cl_context):
    rows = bench_compute.run_divergence(cl_context, n=1 << 18, k=256, degrees=[1, 2])
    assert {r["degree"] for r in rows} == {1, 2}
```

- [x] **Step 3: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_compute.py -v`
Expected: FAIL (`No module named 'gpubench.bench_compute'`) or SKIP.

- [x] **Step 4: Implement `gpubench/bench_compute.py`**

```python
"""Task 1: compute-bound kernel — scaling and warp-divergence sweeps."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyopencl as cl

from . import runner

FLOPS_PER_ITER = 2
_COEF = 0.9999997
_BIAS = 0.0000013
_SRC = Path(__file__).parent / "kernels" / "compute.cl"


def load_source() -> str:
    return _SRC.read_text()


def reference_value(x0: float, k: int) -> float:
    x = np.float32(x0)
    for _ in range(k):
        x = np.float32(np.float32(x * np.float32(_COEF)) + np.float32(_BIAS))
    return float(x)


def _gflops(n: int, k: int, seconds: float) -> float:
    return (FLOPS_PER_ITER * k * n) / seconds / 1e9


def run_scaling(ctx, ns: list[int], k: int) -> list[dict]:
    queue = runner.make_queue(ctx)
    prog = runner.build_program(ctx, load_source(), options=f"-D KITERS={k} -D DEGREE=1")
    rows = []
    for n in ns:
        out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)

        def launch(_n=n, _out=out):
            return prog.compute_uniform(queue, (_n,), None, _out, np.int32(_n))

        secs = runner.time_kernel(queue, launch)
        rows.append({"n": n, "k": k, "seconds": secs, "gflops": _gflops(n, k, secs)})
    return rows


def run_divergence(ctx, n: int, k: int, degrees: list[int]) -> list[dict]:
    queue = runner.make_queue(ctx)
    rows = []
    for d in degrees:
        prog = runner.build_program(ctx, load_source(), options=f"-D KITERS={k} -D DEGREE={d}")
        out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)

        def launch(_out=out):
            return prog.compute_divergent(queue, (n,), None, _out, np.int32(n))

        secs = runner.time_kernel(queue, launch)
        rows.append({"n": n, "k": k, "degree": d, "seconds": secs, "gflops": _gflops(n, k, secs)})
    return rows
```

- [x] **Step 5: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_compute.py -v`
Expected: PASS (or SKIP).

- [x] **Step 6: Commit**

```bash
git add ueb-02/gpubench/kernels/compute.cl ueb-02/gpubench/bench_compute.py ueb-02/tests/test_compute.py
git commit -m "Add Task 1 compute kernel with scaling and divergence sweeps"
```

---

### Task 5: Memory kernel & Task-2 benchmark (`memory.cl`, `bench_memory.py`)

**Files:**
- Create: `gpubench/kernels/memory.cl`
- Create: `gpubench/bench_memory.py`
- Create: `tests/test_memory.py`

**Interfaces:**
- Consumes: `device`, `runner`, `gpubench.SEED`.
- Produces:
  - `PATTERNS = ("coalesced", "strided", "gather")`
  - `make_index(pattern: str, n: int, stride: int, seed: int) -> np.ndarray` (int32 index buffer; for coalesced/strided it is still materialized so the same kernel serves all patterns)
  - `load_source() -> str`
  - `run_patterns(ctx, n: int, stride: int, c: float = 2.0) -> list[dict]` → `{pattern,n,stride,seconds,gbps}`
  - `run_occupancy(ctx, n: int, pattern: str, wg_sizes: list[int]) -> list[dict]` → `{pattern,n,wg,seconds,gbps,wavefronts_per_group}`
  - `effective_gbps(n: int, seconds: float, with_index: bool) -> float`

**Kernel:** `b[i] = a[idx[i]] * c`. The index buffer encodes the pattern (coalesced = identity, strided = `(i*stride)%n`, gather = random permutation), so one kernel times all three honestly (gather pays one extra index read; accounted in bytes).

- [x] **Step 1: Write `gpubench/kernels/memory.cl`**

```c
// Streaming kernel b[i] = a[idx[i]] * c, low arithmetic intensity.
__kernel void stream(__global const float *a,
                     __global float *b,
                     __global const int *idx,
                     const float c,
                     const int n) {
    int i = get_global_id(0);
    if (i >= n) return;
    b[i] = a[idx[i]] * c;
}
```

- [x] **Step 2: Write failing test `tests/test_memory.py`**

```python
import numpy as np
import pyopencl as cl
from gpubench import bench_memory, runner


def test_make_index_gather_is_bijection():
    idx = bench_memory.make_index("gather", n=4096, stride=7, seed=1234)
    assert sorted(idx.tolist()) == list(range(4096))


def test_make_index_coalesced_identity():
    idx = bench_memory.make_index("coalesced", n=16, stride=7, seed=1234)
    assert idx.tolist() == list(range(16))


def test_kernel_computes_a_times_c(cl_context):
    ctx = cl_context
    queue = runner.make_queue(ctx)
    n = 4096
    a = np.arange(n, dtype=np.float32)
    idx = bench_memory.make_index("strided", n=n, stride=3, seed=1234)
    prog = runner.build_program(ctx, bench_memory.load_source())
    mf = cl.mem_flags
    a_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=a)
    idx_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=idx)
    b_buf = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    prog.stream(queue, (n,), None, a_buf, b_buf, idx_buf, np.float32(2.0), np.int32(n)).wait()
    b = np.empty(n, np.float32)
    cl.enqueue_copy(queue, b, b_buf).wait()
    np.testing.assert_allclose(b, a[idx] * 2.0, rtol=1e-5)


def test_run_patterns_reports_bandwidth(cl_context):
    rows = bench_memory.run_patterns(cl_context, n=1 << 18, stride=16)
    assert {r["pattern"] for r in rows} == set(bench_memory.PATTERNS)
    assert all(r["gbps"] > 0 for r in rows)
```

- [x] **Step 3: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_memory.py -v`
Expected: FAIL (`No module named 'gpubench.bench_memory'`) or SKIP (device tests).

- [x] **Step 4: Implement `gpubench/bench_memory.py`**

```python
"""Task 2: memory-bound streaming kernel — patterns and occupancy sweeps."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyopencl as cl

from . import runner
from .device import wavefront_width

PATTERNS = ("coalesced", "strided", "gather")
_SRC = Path(__file__).parent / "kernels" / "memory.cl"


def load_source() -> str:
    return _SRC.read_text()


def make_index(pattern: str, n: int, stride: int, seed: int) -> np.ndarray:
    if pattern == "coalesced":
        return np.arange(n, dtype=np.int32)
    if pattern == "strided":
        return ((np.arange(n, dtype=np.int64) * stride) % n).astype(np.int32)
    if pattern == "gather":
        rng = np.random.default_rng(seed)
        return rng.permutation(n).astype(np.int32)
    raise ValueError(f"unknown pattern: {pattern}")


def effective_gbps(n: int, seconds: float, with_index: bool) -> float:
    # read a + write b (+ read idx for every pattern, materialized buffer)
    floats = 2 * n          # a read, b write
    ints = n                # idx read
    moved = floats * 4 + ints * 4
    return (moved / seconds) / 1e9


def _bench_once(ctx, queue, prog, n, idx, c, local_size=None) -> float:
    mf = cl.mem_flags
    a = np.ones(n, dtype=np.float32)
    a_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=a)
    idx_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=idx)
    b_buf = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    ls = (local_size,) if local_size else None

    def launch():
        return prog.stream(queue, (n,), ls, a_buf, b_buf, idx_buf, np.float32(c), np.int32(n))

    return runner.time_kernel(queue, launch)


def run_patterns(ctx, n: int, stride: int, c: float = 2.0) -> list[dict]:
    from . import SEED
    queue = runner.make_queue(ctx)
    prog = runner.build_program(ctx, load_source())
    rows = []
    for pattern in PATTERNS:
        idx = make_index(pattern, n, stride, SEED)
        secs = _bench_once(ctx, queue, prog, n, idx, c)
        rows.append({
            "pattern": pattern, "n": n, "stride": stride,
            "seconds": secs, "gbps": effective_gbps(n, secs, with_index=True),
        })
    return rows


def run_occupancy(ctx, n: int, pattern: str, wg_sizes: list[int]) -> list[dict]:
    from . import SEED
    queue = runner.make_queue(ctx)
    prog = runner.build_program(ctx, load_source())
    wf = wavefront_width(ctx)
    idx = make_index(pattern, n, 16, SEED)
    rows = []
    for wg in wg_sizes:
        secs = _bench_once(ctx, queue, prog, n, idx, 2.0, local_size=wg)
        rows.append({
            "pattern": pattern, "n": n, "wg": wg, "seconds": secs,
            "gbps": effective_gbps(n, secs, with_index=True),
            "wavefronts_per_group": max(1, wg // wf),
        })
    return rows
```

- [x] **Step 5: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_memory.py -v`
Expected: PASS (or device tests SKIP; `make_index` tests PASS regardless).

- [x] **Step 6: Commit**

```bash
git add ueb-02/gpubench/kernels/memory.cl ueb-02/gpubench/bench_memory.py ueb-02/tests/test_memory.py
git commit -m "Add Task 2 streaming kernel with pattern and occupancy sweeps"
```

---

### Task 6: CPU baselines (`cpu_baseline.py`)

**Files:**
- Create: `gpubench/cpu_baseline.py`
- Create: `tests/test_cpu_baseline.py`

**Interfaces:**
- Consumes: `gpubench.SEED`.
- Produces:
  - `numpy_compute(n: int, k: int) -> dict` → `{backend:"numpy", n,k,seconds,gflops}` (mirrors Task 1 math vectorized; no divergence cost)
  - `numpy_divergence(n: int, k: int, degrees: list[int]) -> list[dict]` → per-degree `{seconds,...}` showing branch cost is ~flat
  - `numpy_stream(n: int) -> dict` and `numpy_gather(n: int) -> dict` → `{pattern,n,seconds,gbps}` (Task 2 contrast: sequential vs cache-miss)

- [x] **Step 1: Write failing test `tests/test_cpu_baseline.py`**

```python
from gpubench import cpu_baseline


def test_numpy_compute_positive():
    r = cpu_baseline.numpy_compute(n=1 << 16, k=64)
    assert r["gflops"] > 0 and r["backend"] == "numpy"


def test_numpy_stream_vs_gather():
    s = cpu_baseline.numpy_stream(n=1 << 20)
    g = cpu_baseline.numpy_gather(n=1 << 20)
    assert s["gbps"] > 0 and g["gbps"] > 0
    assert s["pattern"] == "coalesced" and g["pattern"] == "gather"


def test_numpy_divergence_rows():
    rows = cpu_baseline.numpy_divergence(n=1 << 16, k=64, degrees=[1, 4])
    assert {r["degree"] for r in rows} == {1, 4}
```

- [x] **Step 2: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_cpu_baseline.py -v`
Expected: FAIL (`No module named 'gpubench.cpu_baseline'`).

- [x] **Step 3: Implement `gpubench/cpu_baseline.py`**

```python
"""CPU baselines (NumPy) mirroring the two GPU benchmarks."""
from __future__ import annotations

import time

import numpy as np

from . import SEED
from .bench_compute import FLOPS_PER_ITER, _COEF, _BIAS  # type: ignore


def _time(fn, repeats: int = 5) -> float:
    fn()  # warm-up
    best = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best


def numpy_compute(n: int, k: int) -> dict:
    x = (1.0 + np.arange(n, dtype=np.float32) * np.float32(1e-7))

    def run():
        v = x.copy()
        for _ in range(k):
            v = v * np.float32(_COEF) + np.float32(_BIAS)
        return v

    secs = _time(run)
    return {"backend": "numpy", "n": n, "k": k, "seconds": secs,
            "gflops": (FLOPS_PER_ITER * k * n) / secs / 1e9}


def numpy_divergence(n: int, k: int, degrees: list[int]) -> list[dict]:
    rng = np.random.default_rng(SEED)
    lane = rng.integers(0, 1 << 30, size=n)
    x0 = (1.0 + np.arange(n, dtype=np.float32) * np.float32(1e-7))
    rows = []
    for d in degrees:
        sel = lane % d

        def run():
            v = x0.copy()
            for branch in range(d):
                mask = sel == branch
                vb = v[mask]
                for _ in range(k):
                    vb = vb * np.float32(_COEF) + np.float32(_BIAS)
                v[mask] = vb
            return v

        secs = _time(run)
        rows.append({"backend": "numpy", "n": n, "k": k, "degree": d, "seconds": secs})
    return rows


def _stream_gbps(n: int, secs: float) -> float:
    moved = (2 * n) * 4 + n * 4  # a read + b write + idx read (parity w/ GPU)
    return (moved / secs) / 1e9


def numpy_stream(n: int) -> dict:
    a = np.ones(n, dtype=np.float32)
    idx = np.arange(n, dtype=np.int64)

    def run():
        return a[idx] * np.float32(2.0)

    secs = _time(run)
    return {"backend": "numpy", "pattern": "coalesced", "n": n,
            "seconds": secs, "gbps": _stream_gbps(n, secs)}


def numpy_gather(n: int) -> dict:
    a = np.ones(n, dtype=np.float32)
    idx = np.random.default_rng(SEED).permutation(n)

    def run():
        return a[idx] * np.float32(2.0)

    secs = _time(run)
    return {"backend": "numpy", "pattern": "gather", "n": n,
            "seconds": secs, "gbps": _stream_gbps(n, secs)}
```

- [x] **Step 4: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_cpu_baseline.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add ueb-02/gpubench/cpu_baseline.py ueb-02/tests/test_cpu_baseline.py
git commit -m "Add NumPy CPU baselines for both benchmarks"
```

---

### Task 7: CLI orchestration (`cli.py`)

**Files:**
- Create: `gpubench/cli.py`
- Create: `gpubench/__main__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: all `bench_*`, `cpu_baseline`, `device`.
- Produces:
  - `build_parser() -> argparse.ArgumentParser`
  - `main(argv: list[str] | None = None) -> int`
  - Subcommands: `info`, `compute`, `memory`, `baseline`, `all` (writes JSON into `results/`), `plots` (delegates to Task 8). Common flags: `--device`, `--quick`, `--out results`.
  - JSON written per run: `results/<name>.json` with `{"device": <DeviceInfo dict>, "rows": [...]}`.

- [x] **Step 1: Write failing test `tests/test_cli.py`**

```python
from gpubench import cli


def test_parser_has_subcommands():
    parser = cli.build_parser()
    args = parser.parse_args(["info", "--device", "cpu"])
    assert args.command == "info"
    assert args.device == "cpu"


def test_quick_flag_parses():
    parser = cli.build_parser()
    args = parser.parse_args(["all", "--quick"])
    assert args.quick is True
```

- [x] **Step 2: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_cli.py -v`
Expected: FAIL (`No module named 'gpubench.cli'`).

- [x] **Step 3: Implement `gpubench/cli.py`**

```python
"""Command-line entry point: run benchmarks and dump JSON results."""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from . import bench_compute, bench_memory, cpu_baseline, device


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gpubench", description="GPU SIMT & bandwidth benchmarks")
    p.add_argument("command",
                   choices=["info", "compute", "memory", "baseline", "all", "plots"])
    p.add_argument("--device", default=None, help="gpu | cpu | <index>")
    p.add_argument("--quick", action="store_true", help="small sweeps for a smoke run")
    p.add_argument("--out", default="results", help="output directory for JSON")
    return p


def _write(out_dir: Path, name: str, info, rows) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"device": dataclasses.asdict(info) if info else None, "rows": rows}
    (out_dir / f"{name}.json").write_text(json.dumps(payload, indent=2))


def _sweeps(quick: bool):
    if quick:
        return {
            "ns": [1 << 12, 1 << 16, 1 << 20],
            "degrees": [1, 2, 4, 8],
            "wgs": [16, 64, 256],
            "mem_n": 1 << 20,
        }
    return {
        "ns": [1 << 10, 1 << 13, 1 << 16, 1 << 19, 1 << 22, 1 << 24, 1 << 26],
        "degrees": [1, 2, 4, 8, 16, 32, 64],
        "wgs": [8, 16, 32, 64, 128, 256, 512],
        "mem_n": 1 << 25,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    sw = _sweeps(args.quick)

    if args.command == "plots":
        from . import plots
        plots.generate_all(out, Path("report/essay/figures"))
        return 0

    if args.command == "baseline":
        rows = (
            [cpu_baseline.numpy_compute(n, 256) for n in sw["ns"]]
            + cpu_baseline.numpy_divergence(1 << 20, 256, sw["degrees"])
            + [cpu_baseline.numpy_stream(sw["mem_n"]), cpu_baseline.numpy_gather(sw["mem_n"])]
        )
        _write(out, "baseline", None, rows)
        return 0

    ctx = device.select_context(args.device)
    info = device.query_device_info(ctx)

    if args.command in ("info", "all"):
        _write(out, "device_info", info, [])
    if args.command in ("compute", "all"):
        _write(out, "compute_scaling", info, bench_compute.run_scaling(ctx, sw["ns"], 256))
        _write(out, "compute_divergence", info,
               bench_compute.run_divergence(ctx, sw["mem_n"], 256, sw["degrees"]))
    if args.command in ("memory", "all"):
        _write(out, "memory_patterns", info, bench_memory.run_patterns(ctx, sw["mem_n"], 16))
        _write(out, "memory_occupancy", info,
               bench_memory.run_occupancy(ctx, sw["mem_n"], "coalesced", sw["wgs"]))
    return 0
```

- [x] **Step 4: Write `gpubench/__main__.py`**

```python
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 5: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [x] **Step 6: Smoke-run the CLI (if a device exists) + baseline (always)**

Run: `cd ueb-02 && python -m gpubench baseline --quick && python -m gpubench all --device cpu --quick`
Expected: JSON files appear under `ueb-02/results/`. (The `all` run needs an OpenCL device; on this box install POCL per Task 1, or run on the Windows GPU.)

- [x] **Step 7: Commit**

```bash
git add ueb-02/gpubench/cli.py ueb-02/gpubench/__main__.py ueb-02/tests/test_cli.py
git commit -m "Add CLI orchestration and JSON result dumping"
```

---

### Task 8: Plots from results JSON (`plots.py`)

**Files:**
- Create: `gpubench/plots.py`
- Create: `tests/test_plots.py`

**Interfaces:**
- Consumes: JSON files written by Task 7 (`results/*.json`).
- Produces:
  - `generate_all(results_dir: Path, figures_dir: Path) -> list[Path]`
  - Individual figure functions: `plot_scaling`, `plot_divergence`, `plot_patterns`, `plot_occupancy` — each `(data: dict, out_path: Path) -> Path`.
  - Uses matplotlib `Agg` backend (no display); skips a figure whose JSON is absent.

- [ ] **Step 1: Write failing test `tests/test_plots.py`**

```python
import json
from pathlib import Path

from gpubench import plots


def test_plot_scaling_writes_png(tmp_path):
    data = {"device": {"name": "Test"}, "rows": [
        {"n": 4096, "gflops": 10.0}, {"n": 1 << 20, "gflops": 100.0}]}
    out = tmp_path / "scaling.png"
    result = plots.plot_scaling(data, out)
    assert result.exists() and result.suffix == ".png"


def test_generate_all_handles_missing(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "compute_scaling.json").write_text(json.dumps(
        {"device": {"name": "T"}, "rows": [{"n": 4096, "gflops": 10.0}]}))
    figs = tmp_path / "figs"
    made = plots.generate_all(results, figs)
    assert any(p.name == "scaling.png" for p in made)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ueb-02 && python -m pytest tests/test_plots.py -v`
Expected: FAIL (`No module named 'gpubench.plots'`).

- [ ] **Step 3: Implement `gpubench/plots.py`**

```python
"""Generate report figures from results JSON. GPU not required."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def plot_scaling(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["n"])
    xs = [r["n"] for r in rows]
    ys = [r["gflops"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="o")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Problemgröße n (Work-Items)")
    ax.set_ylabel("Durchsatz (GFLOP/s)")
    ax.set_title("Aufgabe 1: Skalierung über n")
    ax.grid(True, which="both", alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)
    return out_path


def plot_divergence(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["degree"])
    xs = [r["degree"] for r in rows]
    ys = [r["gflops"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="s", color="crimson")
    ax.set_xlabel("Divergenzgrad (Pfade je Wavefront)")
    ax.set_ylabel("Durchsatz (GFLOP/s)")
    ax.set_title("Aufgabe 1: Warp-Divergenz")
    ax.grid(True, alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)
    return out_path


def plot_patterns(data: dict, out_path: Path) -> Path:
    rows = data["rows"]
    xs = [r["pattern"] for r in rows]
    ys = [r["gbps"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(xs, ys, color=["seagreen", "goldenrod", "indianred"])
    ax.set_ylabel("Effektive Bandbreite (GB/s)")
    ax.set_title("Aufgabe 2: Zugriffsmuster")
    ax.grid(True, axis="y", alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)
    return out_path


def plot_occupancy(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["wg"])
    xs = [r["wg"] for r in rows]
    ys = [r["gbps"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="o", color="navy")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Work-Group-Größe")
    ax.set_ylabel("Effektive Bandbreite (GB/s)")
    ax.set_title("Aufgabe 2: Latency-Hiding über Occupancy")
    ax.grid(True, which="both", alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)
    return out_path


def generate_all(results_dir: Path, figures_dir: Path) -> list[Path]:
    jobs = [
        ("compute_scaling.json", plot_scaling, "scaling.png"),
        ("compute_divergence.json", plot_divergence, "divergence.png"),
        ("memory_patterns.json", plot_patterns, "patterns.png"),
        ("memory_occupancy.json", plot_occupancy, "occupancy.png"),
    ]
    made = []
    for fname, fn, out_name in jobs:
        data = _load(results_dir / fname)
        if data and data.get("rows"):
            made.append(fn(data, figures_dir / out_name))
    return made
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ueb-02 && python -m pytest tests/test_plots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ueb-02/gpubench/plots.py ueb-02/tests/test_plots.py
git commit -m "Add matplotlib figure generation from results JSON"
```

---

### Task 9: README & Linux/Windows setup docs

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: human-facing run instructions.

- [ ] **Step 1: Write `README.md`**

````markdown
# Übung 2 — SIMT-Ausführungsmodell & GPU-Speicherbandbreite

Two PyOpenCL micro-benchmarks for Heterogeneous Computing (2026S):

- **Aufgabe 1** — compute-bound kernel; scaling over `n` and warp/wavefront divergence.
- **Aufgabe 2** — memory-bound streaming kernel; coalesced / strided / random-gather
  bandwidth and latency hiding via occupancy.

Runs on **Windows and Linux** with any AMD/NVIDIA/Intel OpenCL device, or on CPU via POCL.

## Setup

### Linux
```bash
sudo apt-get install -y ocl-icd-opencl-dev pocl-opencl-icd ocl-icd-libopencl1 clinfo
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
python -m gpubench plots                       # figures -> report/essay/figures/
```
`--device` accepts `gpu`, `cpu`, or a numeric index; `--quick` runs small sweeps.

## Tests
```bash
python -m pytest -v   # device-bound tests skip automatically if no OpenCL device
```

## Layout
- `gpubench/` — Python package (device, runner, benchmarks, baselines, plots, CLI)
- `gpubench/kernels/*.cl` — the only non-Python source (OpenCL-C)
- `results/` — committed JSON; figures and report regenerate from it without a GPU
- `report/essay/` — LaTeX report (German)
````

- [ ] **Step 2: Verify it renders** (no command; visual check that code blocks are closed).

- [ ] **Step 3: Commit**

```bash
git add ueb-02/README.md
git commit -m "Add README with cross-platform setup and run instructions"
```

---

### Task 10: Run benchmarks & generate result data

> This task produces the real measurement data the report depends on. Run it on a machine
> with a real GPU (the Windows AMD card preferred; Linux iGPU acceptable). If only this
> GPU-less box is available, run with `--device cpu` (POCL) so the pipeline is exercised,
> and note in the report that GPU numbers were taken on the Windows card.

**Files:**
- Modify (generated): `results/*.json`
- Modify (generated): `report/essay/figures/*.png`

**Interfaces:**
- Consumes: Task 7 CLI, Task 8 plots.
- Produces: committed `results/*.json` and `report/essay/figures/*.png` for the report.

- [ ] **Step 1: Run the full GPU sweeps**

Run: `cd ueb-02 && python -m gpubench all --device gpu`
Expected: `results/device_info.json`, `compute_scaling.json`, `compute_divergence.json`, `memory_patterns.json`, `memory_occupancy.json`.

- [ ] **Step 2: Run CPU baselines**

Run: `cd ueb-02 && python -m gpubench baseline`
Expected: `results/baseline.json`.

- [ ] **Step 3: Generate figures**

Run: `cd ueb-02 && python -m gpubench plots`
Expected: `report/essay/figures/scaling.png`, `divergence.png`, `patterns.png`, `occupancy.png`.

- [ ] **Step 4: Sanity-check the numbers**

Confirm: scaling curve rises then plateaus; divergence throughput falls roughly toward `1/degree`; coalesced > strided > gather bandwidth; occupancy curve rises with work-group size. If a curve looks wrong, revisit the relevant `bench_*` module before writing prose around it.

- [ ] **Step 5: Commit**

```bash
git add ueb-02/results/*.json ueb-02/report/essay/figures/*.png
git commit -m "Add measured benchmark results and report figures"
```

---

### Task 11: LaTeX report (`report/essay/report.tex`)

**Files:**
- Create: `report/essay/report.tex`
- Create: `report/essay/references.bib`
- Create: `report/essay/.gitignore`

**Interfaces:**
- Consumes: figures from Task 10 (`figures/*.png`), device facts from `results/device_info.json`.
- Produces: `report.pdf` (built locally), the course deliverable.

**Style:** Copy the preamble/conventions from `ueb-01/report/essay/report.tex` verbatim
(article 12pt, `ngerman` babel, `lmodern`, `geometry` 1in, `fancyhdr`, `graphicx`,
`subcaption`, `booktabs`, `tabularx`, `biblatex` verbose-ibid + bibtex). Header keeps the
author name (`Jan-Niclas Loosen`), `Mat.Nr. UNKENNTLICH`, course `Het. Computing /
Hardware Projekt`, `Universität Trier`, `\today`. Unnumbered `\section*`. German prose,
first-person, `\texttt{}` for identifiers, `\autocite` for references.

- [ ] **Step 1: Write `report/essay/.gitignore`**

```
*.aux
*.log
*.out
*.bbl
*.bcf
*.blg
*.run.xml
*.toc
```

- [ ] **Step 2: Write `report/essay/references.bib`**

```bibtex
@misc{pyopencl,
  author = {Andreas Klöckner},
  title  = {PyOpenCL},
  year   = {2024},
  url    = {https://documen.tician.de/pyopencl/}
}
@misc{opencl,
  author = {{Khronos Group}},
  title  = {The OpenCL Specification},
  year   = {2024},
  url    = {https://www.khronos.org/opencl/}
}
@misc{pocl,
  author = {{POCL contributors}},
  title  = {POCL — Portable Computing Language},
  year   = {2024},
  url    = {http://portablecl.org/}
}
```

- [ ] **Step 3: Write `report/essay/report.tex`**

Use this skeleton; fill the measured numbers from `results/*.json` into the prose and the
results table. Every `<...>` placeholder must be replaced with a real measured value
before the final commit — no `<...>` may remain.

```latex
\documentclass[a4paper, 12pt]{article}
\usepackage[ngerman]{babel}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\usepackage{fancyhdr}
\usepackage{graphicx}
\usepackage{subcaption}
\usepackage{hyperref}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{titlesec}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}
\geometry{a4paper, margin=1in, headsep=35pt}
\titlespacing*{\section}{0pt}{0.6ex plus .1ex minus .1ex}{0.2ex plus .1ex}
\sloppy
\usepackage{csquotes}
\usepackage[style=verbose-ibid,backend=bibtex]{biblatex}
\pagestyle{fancy}
\fancyhead{}
\fancyhead[L]{\veranstaltung}
\fancyhead[C]{\textbf{Jan-Niclas Loosen}\\ \textbf{Mat.Nr. UNKENNTLICH}}
\fancyhead[R]{Universität Trier\\ \today}
\newcommand{\veranstaltung}{Het. Computing\\ Übungsblatt 2}
\bibliography{references.bib}

\begin{document}

\section*{Einführung}
% 1 paragraph: goal — make SIMT visible; two kernels (rechen- vs. speicherintensiv);
% hardware used (AMD <device name from device_info.json>), Messmethodik (PyOpenCL,
% Profiling-Events, Median). Mention CPU-Vergleich via POCL/NumPy.

\section*{Aufbau und Messmethodik}
% PyOpenCL, OpenCL-C-Kernels zur Laufzeit kompiliert; Wavefront = <wavefront> Lanes;
% <compute_units> Compute Units; Zeitmessung über Profiling-Events, Warm-up + Median.

\section*{Aufgabe 1: SIMT und Warp-Divergenz}
% Skalierung: throughput steigt bis Sättigung bei n ~ <value>, Peak <value> GFLOP/s.
\begin{figure}[h!]\centering
\includegraphics[width=0.7\textwidth]{figures/scaling.png}
\caption{Durchsatz über der Problemgröße $n$.}\label{fig:scaling}\end{figure}
% Divergenz: Einbruch von <peak> auf <low> GFLOP/s bei Grad <d>; ~1/d-Verlauf.
\begin{figure}[h!]\centering
\includegraphics[width=0.7\textwidth]{figures/divergence.png}
\caption{Durchsatz über dem Divergenzgrad.}\label{fig:divergence}\end{figure}
% Erklärung: Wavefront führt Lanes im Lockstep; divergente Pfade werden serialisiert
% (Maskierung). CPU: Sprungvorhersage + unabhängige Kerne -> Verzweigung ~kostenlos.
% CPU-Baseline (NumPy/POCL): Divergenzgrad nahezu flach.

\section*{Aufgabe 2: Speicherzugriff und Latency-Hiding}
\begin{figure}[h!]\centering
\includegraphics[width=0.7\textwidth]{figures/patterns.png}
\caption{Effektive Bandbreite je Zugriffsmuster.}\label{fig:patterns}\end{figure}
% coalesced <value> GB/s vs strided <value> vs gather <value>; Verhältnis zu Peak
% <peak_bandwidth> GB/s.
\begin{figure}[h!]\centering
\includegraphics[width=0.7\textwidth]{figures/occupancy.png}
\caption{Bandbreite über der Work-Group-Größe (Occupancy).}\label{fig:occupancy}\end{figure}
% Occupancy = aktive Wavefronts / max. mögliche; Durchsatz steigt, bis genug Wavefronts
% die Speicherlatenz verdecken. CPU verdeckt Latenz über Caches/Prefetch -> sequenziell
% schnell (<value> GB/s), zufällig langsam (<value> GB/s, Cache-Misses).

\section*{Fazit}
\begin{table}[h]\centering
\begin{tabularx}{\textwidth}{l *{2}{>{\centering\arraybackslash}X}}
\toprule
\textbf{Messung} & \textbf{GPU} & \textbf{CPU (NumPy/POCL)} \\
\midrule
Peak GFLOP/s            & <value> & <value> \\
Divergenz-Einbruch      & <value> & <value> \\
Bandbreite coalesced    & <value> & <value> \\
Bandbreite gather       & <value> & <value> \\
\bottomrule
\end{tabularx}
\caption{Zusammenfassung der Messungen.}\label{tab:summary}\end{table}
% 1 Absatz: SIMT verlangt divergenzarme Pfade und coalesced, regelmäßige Datenlayouts;
% Konsequenz für Datenanordnung in GPU-Anwendungen.

\end{document}
```

- [ ] **Step 4: Build the PDF**

Run: `cd ueb-02/report/essay && pdflatex report.tex && bibtex report && pdflatex report.tex && pdflatex report.tex`
Expected: `report.pdf` produced with no unresolved references and **no `<...>` placeholders remaining**.

- [ ] **Step 5: Commit**

```bash
git add ueb-02/report/essay/report.tex ueb-02/report/essay/references.bib ueb-02/report/essay/.gitignore ueb-02/report/essay/report.pdf
git commit -m "Add German LaTeX results report for ueb-02"
```

---

### Task 12: Final verification & PR

**Files:**
- Modify: none (verification + integration).

**Interfaces:**
- Consumes: everything.
- Produces: a pull request against `2026S-HC`.

- [ ] **Step 1: Full test suite**

Run: `cd ueb-02 && python -m pytest -v`
Expected: all PASS (device-bound tests may SKIP on a GPU-less box; none FAIL).

- [ ] **Step 2: Confirm deliverables exist**

Confirm present: `gpubench/` package, `results/*.json`, `report/essay/figures/*.png`,
`report/essay/report.pdf`, `README.md`. Confirm no `<...>` placeholders in `report.tex`.

- [ ] **Step 3: Push branch**

```bash
git push -u origin ueb-02-gpu-benchmarks
```

- [ ] **Step 4: Open PR**

Run: `gh pr create --repo syssoft-hc/2026S-HC --title "Übung 2: SIMT & GPU-Bandbreite" --body "..."`
(Confirm the correct upstream/fork target with the user before pushing/creating the PR.)

---

## Self-Review

**Spec coverage:**
- Task 1 compute kernel + n-scaling + warm-up/saturation → Task 4, Task 10, Task 11. ✓
- Warp divergence sweep + explanation → Task 4 (`run_divergence`), Task 11 prose. ✓
- GFLOP/s throughput → `bench_compute._gflops`. ✓
- Task 2 streaming kernel + 3 patterns → Task 5. ✓
- Effective bandwidth vs device peak → `effective_gbps` + `device.peak_bandwidth_gbps`. ✓
- Occupancy / work-group sweep + reported occupancy estimate → `run_occupancy` (`wavefronts_per_group`), Task 11. ✓
- CPU baseline (empirical) → Task 6 + POCL device path via `--device cpu`. ✓
- Cross-platform Windows/Linux → Task 1 setup, `device.select_context`, README. ✓
- Reproducible from JSON without GPU → Task 7 JSON dump, Task 8 plots, fixed SEED. ✓
- German LaTeX report, ueb-01 style, name kept → Task 11. ✓
- Don't touch `Importer.py`/`cs.*` → not referenced by any task. ✓
- PR against 2026S-HC → Task 12. ✓

**Placeholder scan:** Code steps contain full code. The only intentional `<...>` markers are
measured numbers in `report.tex` (Task 11), which Step 4 of that task explicitly requires to
be replaced before committing — flagged, not silent.

**Type consistency:** `DeviceInfo` fields used identically in `device.py`, `cli._write`
(`dataclasses.asdict`), and report prose. `run_scaling`/`run_divergence` row keys
(`n,k,degree,seconds,gflops`) match `plots.plot_scaling`/`plot_divergence` access. `run_patterns`/
`run_occupancy` keys (`pattern,gbps,wg`) match `plots.plot_patterns`/`plot_occupancy`. `load_source`
defined in both `bench_compute` and `bench_memory` (distinct modules, intentional). `_COEF`/`_BIAS`
imported by `cpu_baseline` from `bench_compute`. Consistent.
