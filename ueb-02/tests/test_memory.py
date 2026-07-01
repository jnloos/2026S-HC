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
    rows = bench_memory.run_patterns(cl_context, n=1 << 18, stride=521)
    assert {r["pattern"] for r in rows} == set(bench_memory.PATTERNS)
    assert all(r["gbps"] > 0 for r in rows)
    bw = {r["pattern"]: r["gbps"] for r in rows}
    # Coalesced is the fastest access pattern on any coalescing/cache hardware;
    # strided and gather both defeat it.
    assert all(bw["coalesced"] >= bw[p] for p in bw if p != "coalesced")


def test_make_index_gather_is_deterministic():
    from gpubench import SEED
    a = bench_memory.make_index("gather", 4096, 521, SEED)
    b = bench_memory.make_index("gather", 4096, 521, SEED)
    assert np.array_equal(a, b)
    c = bench_memory.make_index("gather", 4096, 521, SEED + 1)
    assert not np.array_equal(a, c)


def test_make_index_strided_rejects_non_coprime():
    import pytest
    with pytest.raises(ValueError):
        bench_memory.make_index("strided", n=4096, stride=16, seed=1234)


def test_run_occupancy_handles_indivisible_n(cl_context):
    # n is not a multiple of any wg here; the launch must pad the global size
    # instead of raising CL_INVALID_WORK_GROUP_SIZE.
    n = (1 << 16) + 7
    rows = bench_memory.run_occupancy(cl_context, n=n, pattern="coalesced", wg_sizes=[16, 64])
    assert {r["wg"] for r in rows} == {16, 64}
    assert all(r["gbps"] > 0 for r in rows)

