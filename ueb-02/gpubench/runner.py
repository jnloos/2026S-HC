"""Build OpenCL programs and time kernels with profiling events."""
from __future__ import annotations

from statistics import median
from typing import Callable

import pyopencl as cl


def make_queue(ctx: cl.Context) -> cl.CommandQueue:
    return cl.CommandQueue(
        ctx, properties=cl.command_queue_properties.PROFILING_ENABLE
    )


def build_program(ctx: cl.Context, src: str, options: str = "") -> cl.Program:
    return cl.Program(ctx, src).build(options=options)


def _event_seconds(ev: cl.Event) -> float:
    ev.wait()
    return (ev.profile.end - ev.profile.start) * 1e-9


def time_event(events: list[cl.Event]) -> float:
    """Median kernel seconds across already-enqueued profiling events."""
    return median(_event_seconds(ev) for ev in events)


def time_kernel(
    queue: cl.CommandQueue,
    launch: Callable[[], cl.Event],
    *,
    warmup: int = 2,
    repeats: int = 7,
) -> float:
    """Run `launch` warmup+repeats times; return median kernel seconds."""
    for _ in range(warmup):
        _event_seconds(launch())
    samples = [_event_seconds(launch()) for _ in range(repeats)]
    return median(samples)
