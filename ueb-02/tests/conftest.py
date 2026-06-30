import pytest

try:
    import pyopencl as cl
except Exception:  # import guard: tests skip when pyopencl is missing
    cl = None


def _first_device():
    if cl is None:
        return None
    try:
        for platform in cl.get_platforms():
            devs = platform.get_devices()
            if devs:
                return devs[0]
    except Exception:
        return None
    return None


@pytest.fixture(scope="session")
def cl_context():
    """A pyopencl.Context on any available device, or skip if none."""
    if cl is None:
        pytest.skip("pyopencl not installed")
    dev = _first_device()
    if dev is None:
        pytest.skip("no OpenCL device available")
    return cl.Context([dev])
