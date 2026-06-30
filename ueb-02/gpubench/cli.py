"""Command-line entry point: run benchmarks and dump JSON results."""
from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from . import bench_compute, bench_memory, cpu_baseline, device


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gpubench", description="GPU SIMT and bandwidth benchmarks")
    p.add_argument("command",
                   choices=["info", "compute", "memory", "baseline", "all", "plots", "values"])
    p.add_argument("--device", default=None, help="gpu | cpu | <index>")
    p.add_argument("--quick", action="store_true", help="small sweeps for a smoke run")
    p.add_argument("--out", default="results", help="output directory for JSON")
    return p


def _write(out_dir: Path, name: str, info, rows, extra: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"device": dataclasses.asdict(info) if info else None, "rows": rows}
    if extra:
        payload.update(extra)
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

    if args.command == "values":
        from . import report_values
        report_values.generate_values(out, Path("report/essay/values.tex"))
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
        # peak copy bandwidth is the reference for the Task 2 numbers; store it
        # alongside the device facts so the report can cite it without a device.
        peak = device.peak_bandwidth_gbps(ctx, nbytes=64 * 1024 * 1024)
        _write(out, "device_info", info, [], extra={"peak_bandwidth_gbps": peak})
    if args.command in ("compute", "all"):
        _write(out, "compute_scaling", info, bench_compute.run_scaling(ctx, sw["ns"], 256))
        _write(out, "compute_divergence", info,
               bench_compute.run_divergence(ctx, sw["mem_n"], 256, sw["degrees"]))
    if args.command in ("memory", "all"):
        # stride 521 is prime, hence coprime to the power-of-two mem_n, so the
        # strided pattern sweeps the whole array with a large (uncoalesced) gap.
        _write(out, "memory_patterns", info, bench_memory.run_patterns(ctx, sw["mem_n"], 521))
        _write(out, "memory_occupancy", info,
               bench_memory.run_occupancy(ctx, sw["mem_n"], "coalesced", sw["wgs"]))
    return 0
