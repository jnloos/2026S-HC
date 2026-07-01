"""Generate report figures from results JSON. GPU not required."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


# Bandwidth-per-pattern colors keyed by name so bar tint follows the access
# pattern regardless of row order in the results JSON.
_PATTERN_COLORS = {"coalesced": "seagreen", "strided": "goldenrod", "gather": "indianred"}


def _finish(fig, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_scaling(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["n"])
    xs = [r["n"] for r in rows]
    ys = [r["gflops"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="o")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Problemgröße n (Work-Items)")
    ax.set_ylabel("Durchsatz (GFLOP/s)")
    ax.set_title("Aufgabe 1: Skalierung über n")
    ax.grid(True, which="both", alpha=0.3)
    return _finish(fig, out_path)


def plot_divergence(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["degree"])
    xs = [r["degree"] for r in rows]
    ys = [r["gflops"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="s", color="crimson")
    ax.set_xlabel("Divergenzgrad (Pfade je Wavefront)")
    ax.set_ylabel("Durchsatz (GFLOP/s)")
    ax.set_title("Aufgabe 1: Warp-Divergenz")
    ax.grid(True, alpha=0.3)
    return _finish(fig, out_path)


def plot_patterns(data: dict, out_path: Path) -> Path:
    order = list(_PATTERN_COLORS)
    rows = sorted(data["rows"], key=lambda r: order.index(r["pattern"]))
    xs = [r["pattern"] for r in rows]
    ys = [r["gbps"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(xs, ys, color=[_PATTERN_COLORS[r["pattern"]] for r in rows])
    ax.set_ylabel("Effektive Bandbreite (GB/s)")
    ax.set_title("Aufgabe 2: Zugriffsmuster")
    ax.grid(True, axis="y", alpha=0.3)
    return _finish(fig, out_path)


def plot_occupancy(data: dict, out_path: Path) -> Path:
    rows = sorted(data["rows"], key=lambda r: r["wg"])
    xs = [r["wg"] for r in rows]
    ys = [r["gbps"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, marker="o", color="navy")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Work-Group-Größe")
    ax.set_ylabel("Effektive Bandbreite (GB/s)")
    ax.set_title("Aufgabe 2: Latency-Hiding über Occupancy")
    ax.grid(True, which="both", alpha=0.3)
    return _finish(fig, out_path)


def generate_all(results_dir: Path, figures_dir: Path) -> list[Path]:
    jobs = [
        ("compute_scaling.json", plot_scaling, "scaling.png"),
        ("compute_divergence.json", plot_divergence, "divergence.png"),
        ("memory_patterns.json", plot_patterns, "patterns.png"),
        ("memory_occupancy.json", plot_occupancy, "occupancy.png"),
    ]
    made = []
    for fname, fn, out_name in jobs:
        data = _load(results_dir / fname)
        if data and data.get("rows"):
            made.append(fn(data, figures_dir / out_name))
    return made
