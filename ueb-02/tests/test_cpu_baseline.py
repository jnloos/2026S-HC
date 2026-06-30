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
