"""Task 2: memory-bound streaming kernel, patterns and occupancy sweeps."""
from __future__ import annotations

from math import gcd
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
        # (i*stride) % n is a bijection over [0, n) only when stride and n are
        # coprime; otherwise it collapses onto n / gcd distinct addresses and
        # the access stops being a genuine full-array strided sweep.
        if gcd(stride, n) != 1:
            raise ValueError(
                f"strided pattern needs stride coprime to n; gcd({stride}, {n}) "
                f"= {gcd(stride, n)} would touch only {n // gcd(stride, n)} of {n} elements"
            )
        return ((np.arange(n, dtype=np.int64) * stride) % n).astype(np.int32)
    if pattern == "gather":
        rng = np.random.default_rng(seed)
        return rng.permutation(n).astype(np.int32)
    raise ValueError(f"unknown pattern: {pattern}")


def effective_gbps(n: int, seconds: float, with_index: bool) -> float:
    floats = 2 * n          # a read, b write
    moved = floats * 4
    if with_index:
        moved += n * 4      # idx read (materialized for every pattern)
    return (moved / seconds) / 1e9


def _bench_once(ctx, queue, prog, n, idx, c, local_size=None) -> float:
    mf = cl.mem_flags
    a = np.ones(n, dtype=np.float32)
    a_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=a)
    idx_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=idx)
    b_buf = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    stream = cl.Kernel(prog, "stream")  # retrieve once; reuse across launches

    if local_size:
        ls = (local_size,)
        # OpenCL requires global size to be a multiple of the local size; pad up
        # and let the kernel's `if (i >= n) return` guard drop the extra items.
        gsize = (-(-n // local_size)) * local_size
    else:
        ls = None
        gsize = n

    def launch():
        return stream(queue, (gsize,), ls, a_buf, b_buf, idx_buf, np.float32(c), np.int32(n))

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
    # stride is fixed to 1 below, so only patterns that ignore stride are valid;
    # a strided pattern would silently degrade to the identity (coalesced).
    assert pattern in ("coalesced", "gather"), f"run_occupancy: unsupported pattern {pattern!r}"
    from . import SEED
    queue = runner.make_queue(ctx)
    prog = runner.build_program(ctx, load_source())
    wf = wavefront_width(ctx)
    dev_max_wg = ctx.devices[0].max_work_group_size
    idx = make_index(pattern, n, 1, SEED)  # coalesced/gather ignore stride
    rows = []
    for wg in wg_sizes:
        if wg > dev_max_wg:
            continue  # skip work-group sizes the device cannot launch
        secs = _bench_once(ctx, queue, prog, n, idx, 2.0, local_size=wg)
        rows.append({
            "pattern": pattern, "n": n, "wg": wg, "seconds": secs,
            "gbps": effective_gbps(n, secs, with_index=True),
            "wavefronts_per_group": max(1, wg // wf),
        })
    return rows
