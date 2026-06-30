// Configurable arithmetic load, one work-item per element.
// Build-time: -D KITERS=<k> -D DEGREE=<d>
#ifndef KITERS
#define KITERS 256
#endif
#ifndef DEGREE
#define DEGREE 1
#endif

#define COEF 0.9999997f
#define BIAS 0.0000013f

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
    // Each branch does identical work; divergence forces serialization.
    switch (lane) {
        case 0: x = work(x); break;
        case 1: x = work(x); break;
        case 2: x = work(x); break;
        case 3: x = work(x); break;
        case 4: x = work(x); break;
        case 5: x = work(x); break;
        case 6: x = work(x); break;
        case 7: x = work(x); break;
        default: {
            // lanes >= 8 fan out further by their own id
            for (int s = 0; s < lane; ++s) x = work(x) * 1.0f;
            break;
        }
    }
    out[gid] = x;
}
