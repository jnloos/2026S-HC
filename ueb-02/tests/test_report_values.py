import json
from pathlib import Path

from gpubench import report_values


def _seed_results(d: Path, dtype: str = "CPU") -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "device_info.json").write_text(json.dumps({
        "device": {"name": "Test Device", "dtype": dtype, "compute_units": 8,
                   "max_work_group_size": 256, "wavefront": 64, "max_clock_mhz": 1500,
                   "global_mem_bytes": 8 * 2 ** 30, "local_mem_bytes": 65536},
        "rows": [], "peak_bandwidth_gbps": 100.0}))
    (d / "compute_scaling.json").write_text(json.dumps({"device": {}, "rows": [
        {"n": 1024, "k": 256, "seconds": 1.0, "gflops": 5.0},
        {"n": 1 << 20, "k": 256, "seconds": 1.0, "gflops": 50.0}]}))
    (d / "compute_divergence.json").write_text(json.dumps({"device": {}, "rows": [
        {"degree": 1, "gflops": 50.0}, {"degree": 64, "gflops": 10.0}]}))
    (d / "memory_patterns.json").write_text(json.dumps({"device": {}, "rows": [
        {"pattern": "coalesced", "gbps": 90.0}, {"pattern": "strided", "gbps": 20.0},
        {"pattern": "gather", "gbps": 9.0}]}))
    (d / "memory_occupancy.json").write_text(json.dumps({"device": {}, "rows": [
        {"wg": 8, "gbps": 30.0}, {"wg": 512, "gbps": 88.0}]}))
    (d / "baseline.json").write_text(json.dumps({"device": None, "rows": [
        {"backend": "numpy", "n": 1024, "k": 256, "gflops": 12.0},
        {"backend": "numpy", "pattern": "coalesced", "n": 1024, "gbps": 5.0},
        {"backend": "numpy", "pattern": "gather", "n": 1024, "gbps": 1.0}]}))


def test_macros_carry_measured_values(tmp_path):
    _seed_results(tmp_path)
    macros = report_values.build_macros(tmp_path)
    assert macros["computeUnits"] == "8"
    assert macros["waveFront"] == "64"
    assert macros["peakGflops"] == "50{,}0"
    assert macros["bwCoalesced"] == "90{,}0"
    assert macros["bwPeakCopy"] == "100{,}0"
    assert macros["divDegHigh"] == "64"
    assert macros["_is_gpu"] is False


def test_render_sets_cpu_flag_and_defines_commands(tmp_path):
    _seed_results(tmp_path, dtype="CPU")
    out = report_values.generate_values(tmp_path, tmp_path / "values.tex")
    text = out.read_text()
    assert "\\devicegpufalse" in text
    assert "\\newcommand{\\computeUnits}{8}" in text
    assert "\\newif\\ifdevicegpu" in text


def test_render_sets_gpu_flag(tmp_path):
    _seed_results(tmp_path, dtype="GPU")
    text = report_values.generate_values(tmp_path, tmp_path / "values.tex").read_text()
    assert "\\devicegputrue" in text
