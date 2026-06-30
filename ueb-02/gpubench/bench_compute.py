"""Task 1: compute-bound kernel, scaling and warp-divergence sweeps."""
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
    kernel = cl.Kernel(prog, "compute_uniform")  # retrieve once; reuse per launch
    rows = []
    for n in ns:
        out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)

        def launch(_n=n, _out=out):
            return kernel(queue, (_n,), None, _out, np.int32(_n))

        secs = runner.time_kernel(queue, launch)
        rows.append({"n": n, "k": k, "seconds": secs, "gflops": _gflops(n, k, secs)})
    return rows


def run_divergence(ctx, n: int, k: int, degrees: list[int]) -> list[dict]:
    queue = runner.make_queue(ctx)
    src = load_source()  # read once; only the -D DEGREE build option changes
    rows = []
    for d in degrees:
        prog = runner.build_program(ctx, src, options=f"-D KITERS={k} -D DEGREE={d}")
        kernel = cl.Kernel(prog, "compute_divergent")  # retrieve once per build
        out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, size=n * 4)

        def launch(_out=out, _k=kernel):
            return _k(queue, (n,), None, _out, np.int32(n))

        secs = runner.time_kernel(queue, launch)
        rows.append({"n": n, "k": k, "degree": d, "seconds": secs, "gflops": _gflops(n, k, secs)})
    return rows
