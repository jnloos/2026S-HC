#include <pybind11/pybind11.h>
#include <ctime>
#include <cstdio>
#include <unistd.h>

namespace py = pybind11;

double measure_context_switch(int iterations) {
    std::clock_t start = std::clock();

    for (int i = 0; i < iterations; ++i) {
        sleep(0);
    }

    std::clock_t end = std::clock();
    double time_spent = static_cast<double>(end - start) / CLOCKS_PER_SEC;

    std::printf("Time taken: %f seconds\n", time_spent);
    std::printf("Iterations: %d\n", iterations);
    std::printf("Average time per call: %f seconds\n", time_spent / iterations);

    return time_spent;
}

PYBIND11_MODULE(cs, m) {
    m.doc() = "Context switch measurement (C++)";
    m.def("measure_context_switch", &measure_context_switch, py::arg("iterations"),
          "Measure time spent performing iterations of sleep(0)");
}