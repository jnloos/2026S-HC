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
