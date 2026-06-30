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

        def run(_sel=sel, _d=d):
            v = x0.copy()
            for branch in range(_d):
                mask = _sel == branch
                vb = v[mask]
                for _ in range(k):
                    vb = vb * np.float32(_COEF) + np.float32(_BIAS)
                v[mask] = vb
            return v

        secs = _time(run)
        rows.append({"backend": "numpy", "n": n, "k": k, "degree": d, "seconds": secs})
    return rows


def _stream_gbps(n: int, secs: float) -> float:
    moved = (2 * n) * 4 + n * 4  # a read + b write + idx read (parity with GPU)
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
