import math

import numpy as np
import pyopencl as cl
import pytest
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


def test_run_divergence_reports_all_degrees(cl_context):
    rows = bench_compute.run_divergence(cl_context, n=1 << 18, k=256, degrees=[1, 2])
    assert {r["degree"] for r in rows} == {1, 2}
    # Holds on any device: useful work per item is DEGREE-independent, so
    # throughput must stay finite and positive regardless of divergence.
    assert all(r["gflops"] > 0 and math.isfinite(r["gflops"]) for r in rows)


def test_run_divergence_degrades_on_gpu(cl_context):
    # Wavefront serialization is a real-GPU effect; POCL-CPU has no wavefronts,
    # so the throughput collapse only appears on an actual SIMT device.
    if cl_context.devices[0].type != cl.device_type.GPU:
        pytest.skip("divergence throughput collapse only occurs on a SIMT GPU")
    rows = bench_compute.run_divergence(cl_context, n=1 << 20, k=256, degrees=[1, 2])
    by_deg = {r["degree"]: r["gflops"] for r in rows}
    assert by_deg[2] < by_deg[1]
