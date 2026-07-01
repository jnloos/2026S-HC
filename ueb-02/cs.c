#include <time.h>
#include <stdio.h>
#include <unistd.h>

double measure_context_switch(int iterations) {
    // Measure time
    clock_t start = clock();

    // System call loop
    for (int i = 0; i < iterations; i++) {
        sleep(0);
    }

    // Measure time
    clock_t end = clock();
    double time_spent = (double)(end - start) / CLOCKS_PER_SEC;

    printf("Time taken: %f seconds\n", time_spent);
    printf("Iterations: %d\n", iterations);
    printf("Average time per call: %f seconds\n", time_spent / iterations);

    return time_spent;
}