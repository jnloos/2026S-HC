def test_gpubench_imports():
    import gpubench
    assert gpubench.SEED == 1234


def test_pyopencl_importable():
    import pyopencl as cl
    assert hasattr(cl, "get_platforms")


def test_context_or_skip(cl_context):
    # If a device exists, the fixture yields a usable context.
    assert len(cl_context.devices) >= 1
