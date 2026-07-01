// Configurable arithmetic load, one work-item per element.
// Build-time: -D KITERS=<k> -D DEGREE=<d>
#ifndef KITERS
#define KITERS 256
#endif
#ifndef DEGREE
#define DEGREE 1
#endif

// Fallback values so the kernel compiles standalone; the authoritative
// copy lives in bench_compute.py and is injected via -D COEF / -D BIAS.
#ifndef COEF
#define COEF 0.9999997f
#endif
#ifndef BIAS
#define BIAS 0.0000013f
#endif

inline float work(float x) {
    for (int i = 0; i < KITERS; ++i) {
        x = x * COEF + BIAS;   // 2 FLOPs
    }
    return x;
}

__kernel void compute_uniform(__global float *out, const int n) {
    int gid = get_global_id(0);
    if (gid >= n) return;
    float x = 1.0f + gid * 1e-7f;
    out[gid] = work(x);
}

__kernel void compute_divergent(__global float *out, const int n) {
    int gid = get_global_id(0);
    if (gid >= n) return;
    float x = 1.0f + gid * 1e-7f;
    int lane = get_local_id(0) % DEGREE;
    // Every work-item runs work() exactly once, but in a different loop
    // iteration chosen by its lane. Within a wavefront the DEGREE lane
    // groups take their branch on different iterations, so the hardware
    // serializes DEGREE equal-cost paths while the useful work per item
    // (and thus the FLOP count) stays constant for any DEGREE.
    for (int b = 0; b < DEGREE; ++b) {
        if (lane == b) {
            x = work(x);
        }
    }
    out[gid] = x;
}
