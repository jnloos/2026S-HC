import pytest
from gpubench import device


def test_query_device_info(cl_context):
    info = device.query_device_info(cl_context)
    assert info.name
    assert info.compute_units >= 1
    assert info.max_work_group_size >= 1
    assert info.global_mem_bytes > 0


def test_wavefront_width_is_power_of_two(cl_context):
    w = device.wavefront_width(cl_context)
    assert w >= 1
    assert (w & (w - 1)) == 0  # power of two (1,8,16,32,64...)


def test_peak_bandwidth_positive(cl_context):
    bw = device.peak_bandwidth_gbps(cl_context, nbytes=8 * 1024 * 1024)
    assert bw > 0
