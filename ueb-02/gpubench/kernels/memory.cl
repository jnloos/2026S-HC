// Streaming kernel b[i] = a[idx[i]] * c, low arithmetic intensity.
__kernel void stream(__global const float *a,
                     __global float *b,
                     __global const int *idx,
                     const float c,
                     const int n) {
    int i = get_global_id(0);
    if (i >= n) return;
    b[i] = a[idx[i]] * c;
}
