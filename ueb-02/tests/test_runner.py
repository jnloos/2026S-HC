import numpy as np
import pyopencl as cl
from gpubench import runner


def test_time_kernel_runs_and_is_positive(cl_context):
    ctx = cl_context
    queue = runner.make_queue(ctx)
    n = 1 << 16
    prog = runner.build_program(
        ctx, "__kernel void k(__global float*a){int i=get_global_id(0); a[i]+=1.0f;}"
    )
    a = cl.Buffer(ctx, cl.mem_flags.READ_WRITE, size=n * 4)
    cl.enqueue_copy(queue, a, np.zeros(n, np.float32))
    kernel = cl.Kernel(prog, "k")  # retrieve once; reuse across launches

    def launch():
        return kernel(queue, (n,), None, a)

    secs = runner.time_kernel(queue, launch, warmup=1, repeats=3)
    assert secs > 0
