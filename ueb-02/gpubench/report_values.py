"""Generate a LaTeX macro file (values.tex) from the results JSON.

The report \\input's this file and uses the macros instead of hard-coded
numbers, so the prose and table adapt to whatever machine produced the data.
A \\ifdevicegpu boolean lets the report switch GPU vs. CPU wording.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_FILES = (
    "device_info",
    "compute_scaling",
    "compute_divergence",
    "memory_patterns",
    "memory_occupancy",
    "baseline",
)


def _load(results_dir: Path, name: str) -> dict | None:
    path = results_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _de(x: float, prec: int = 1) -> str:
    """German decimal for math mode, e.g. 20.66 -> '20{,}7'."""
    return f"{x:.{prec}f}".replace(".", "{,}")


def _sci(n: int) -> str:
    """n as a math-mode mantissa/exponent, e.g. 67108864 -> '6{,}7 \\cdot 10^{7}'."""
    if n <= 0:
        return "0"
    exp = int(math.floor(math.log10(n)))
    mant = n / 10 ** exp
    return f"{_de(mant)} \\cdot 10^{{{exp}}}"


def _tex_escape(s: str) -> str:
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"),
                 ("$", "\\$"), ("#", "\\#"), ("_", "\\_"),
                 ("{", "\\{"), ("}", "\\}")):
        s = s.replace(a, b)
    return s


def build_macros(results_dir: Path) -> dict[str, str]:
    """Compute every macro value from the JSON results. Missing data -> '?'."""
    di = _load(results_dir, "device_info")
    sc = _load(results_dir, "compute_scaling")
    dv = _load(results_dir, "compute_divergence")
    pa = _load(results_dir, "memory_patterns")
    oc = _load(results_dir, "memory_occupancy")
    bl = _load(results_dir, "baseline")

    m: dict[str, str] = {}
    is_gpu = False

    if di and di.get("device"):
        d = di["device"]
        is_gpu = d.get("dtype") == "GPU"
        m["deviceName"] = _tex_escape(d.get("name", "?"))
        m["deviceType"] = d.get("dtype", "?")
        m["computeUnits"] = str(d.get("compute_units", "?"))
        m["maxWorkGroup"] = str(d.get("max_work_group_size", "?"))
        m["waveFront"] = str(d.get("wavefront", "?"))
        m["maxClock"] = str(d.get("max_clock_mhz", "?"))
        gb = d.get("global_mem_bytes")
        m["globalMemGiB"] = _de(gb / 2 ** 30) if gb else "?"
        peak = di.get("peak_bandwidth_gbps")
        m["bwPeakCopy"] = _de(peak) if peak else "?"

    if sc and sc.get("rows"):
        rows = sc["rows"]
        peak_row = max(rows, key=lambda r: r["gflops"])
        m["peakGflops"] = _de(peak_row["gflops"])
        m["satN"] = _sci(peak_row["n"])
        small = min(rows, key=lambda r: r["n"])
        m["smallGflops"] = _de(small["gflops"])
        m["smallN"] = str(small["n"])

    if dv and dv.get("rows"):
        rows = sorted(dv["rows"], key=lambda r: r["degree"])
        hi, lo = rows[0], rows[-1]
        m["divHigh"] = _de(hi["gflops"])
        m["divLow"] = _de(lo["gflops"])
        m["divDegHigh"] = str(lo["degree"])
        m["divFactor"] = _de(hi["gflops"] / lo["gflops"]) if lo["gflops"] else "?"

    if pa and pa.get("rows"):
        bw = {r["pattern"]: r["gbps"] for r in pa["rows"]}
        m["bwCoalesced"] = _de(bw.get("coalesced", 0))
        m["bwStrided"] = _de(bw.get("strided", 0))
        m["bwGather"] = _de(bw.get("gather", 0))
        if bw.get("gather"):
            m["bwRatio"] = _de(bw["coalesced"] / bw["gather"])

    if oc and oc.get("rows"):
        rows = sorted(oc["rows"], key=lambda r: r["wg"])
        m["occLow"] = _de(rows[0]["gbps"])
        m["occHigh"] = _de(rows[-1]["gbps"])
        m["occWgLow"] = str(rows[0]["wg"])
        m["occWgHigh"] = str(rows[-1]["wg"])

    if bl and bl.get("rows"):
        comp = [r for r in bl["rows"] if "gflops" in r]
        if comp:
            m["npPeakGflops"] = _de(max(r["gflops"] for r in comp))
        stream = [r for r in bl["rows"] if r.get("pattern") == "coalesced"]
        gather = [r for r in bl["rows"] if r.get("pattern") == "gather"]
        if stream:
            m["npStream"] = _de(stream[0]["gbps"])
        if gather:
            m["npGather"] = _de(gather[0]["gbps"])

    m["_is_gpu"] = is_gpu  # consumed by render, not emitted as a string macro
    return m


def render(macros: dict[str, str]) -> str:
    is_gpu = macros.pop("_is_gpu", False)
    lines = [
        "% Auto-generated from results/*.json by gpubench.report_values.",
        "% Do not edit by hand; run `python -m gpubench values` (or run_all.sh).",
        "\\newif\\ifdevicegpu",
        "\\devicegputrue" if is_gpu else "\\devicegpufalse",
    ]
    for name in sorted(macros):
        lines.append(f"\\newcommand{{\\{name}}}{{{macros[name]}}}")
    return "\n".join(lines) + "\n"


def generate_values(results_dir: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(build_macros(results_dir)))
    return out_path
