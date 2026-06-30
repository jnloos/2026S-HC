"""OpenCL device discovery, info query, and a peak-bandwidth probe."""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pyopencl as cl


@dataclass
class DeviceInfo:
    name: str
    dtype: str
    compute_units: int
    max_work_group_size: int
    wavefront: int
    global_mem_bytes: int
    max_clock_mhz: int
    local_mem_bytes: int


def _all_devices():
    out = []
    for platform in cl.get_platforms():
        for dev in platform.get_devices():
            out.append(dev)
    return out


def select_context(selector: str | None = None) -> cl.Context:
    """Pick a context. selector: 'gpu' | 'cpu' | '<index>' | None.

    None prefers a GPU, else the first device. PYOPENCL_CTX is honored when
    selector is None.
    """
    if selector is None and os.environ.get("PYOPENCL_CTX"):
        return cl.create_some_context(interactive=False)

    devices = _all_devices()
    if not devices:
        raise RuntimeError("no OpenCL devices available")

    if selector in (None, "gpu"):
        gpus = [d for d in devices if d.type & cl.device_type.GPU]
        if gpus:
            return cl.Context([gpus[0]])
        if selector == "gpu":
            raise RuntimeError("no GPU device available")
        return cl.Context([devices[0]])
    if selector == "cpu":
        cpus = [d for d in devices if d.type & cl.device_type.CPU]
        if not cpus:
            raise RuntimeError("no CPU device available")
        return cl.Context([cpus[0]])
    # numeric index
    idx = int(selector)
    return cl.Context([devices[idx]])


def _type_name(dev) -> str:
    if dev.type & cl.device_type.GPU:
        return "GPU"
    if dev.type & cl.device_type.CPU:
        return "CPU"
    return "OTHER"


def query_device_info(ctx: cl.Context) -> DeviceInfo:
    dev = ctx.devices[0]
    return DeviceInfo(
        name=dev.name.strip(),
        dtype=_type_name(dev),
        compute_units=dev.max_compute_units,
        max_work_group_size=dev.max_work_group_size,
        wavefront=wavefront_width(ctx),
        global_mem_bytes=dev.global_mem_size,
        max_clock_mhz=dev.max_clock_frequency,
        local_mem_bytes=dev.local_mem_size,
    )


_PROBE_SRC = "__kernel void probe(__global float *a){ a[get_global_id(0)] *= 2.0f; }"


def wavefront_width(ctx: cl.Context) -> int:
    """Wavefront/warp width = preferred work-group-size multiple of a kernel."""
    dev = ctx.devices[0]
    prog = cl.Program(ctx, _PROBE_SRC).build()
    return prog.probe.get_work_group_info(
        cl.kernel_work_group_info.PREFERRED_WORK_GROUP_SIZE_MULTIPLE, dev
    )


def peak_bandwidth_gbps(ctx: cl.Context, nbytes: int = 256 * 1024 * 1024) -> float:
    """Measured copy bandwidth (read+write) as a peak reference for Task 2."""
    n = nbytes // 4
    queue = cl.CommandQueue(ctx, properties=cl.command_queue_properties.PROFILING_ENABLE)
    mf = cl.mem_flags
    a = cl.Buffer(ctx, mf.READ_ONLY, size=n * 4)
    b = cl.Buffer(ctx, mf.WRITE_ONLY, size=n * 4)
    host = np.ones(n, dtype=np.float32)
    cl.enqueue_copy(queue, a, host)
    prog = cl.Program(ctx, "__kernel void cpy(__global const float*a,__global float*b){"
                           "int i=get_global_id(0); b[i]=a[i];}").build()
    cpy = cl.Kernel(prog, "cpy")  # retrieve once; reuse across the timing loop
    # warm-up
    cpy(queue, (n,), None, a, b).wait()
    best = None
    for _ in range(5):
        ev = cpy(queue, (n,), None, a, b)
        ev.wait()
        secs = (ev.profile.end - ev.profile.start) * 1e-9
        best = secs if best is None else min(best, secs)
    moved = 2 * n * 4  # read a + write b
    return (moved / best) / 1e9
