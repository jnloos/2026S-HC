"""Debug middleware: records requests, classifies variants, skips internals."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.debug import bus
from app.debug.middleware import DebugMiddleware


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._reset_for_tests()
    yield
    bus._reset_for_tests()


def _make_app() -> FastAPI:
    """Standalone app — avoids depending on the main app's import-time wiring."""
    app = FastAPI()
    app.add_middleware(DebugMiddleware)

    @app.get("/pools/{pid}")
    async def get_pool(pid: int):
        return {"id": pid}

    @app.post("/pools/{pid}/choose-by-context")
    async def choose_context(pid: int):
        return {"ok": True}

    @app.post("/pools/{pid}/choose-by-img")
    async def choose_img(pid: int):
        return {"ok": True}

    @app.get("/something/else")
    async def other():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/debug/anything")
    async def debug_path():
        return {"ok": True}

    return app


async def _request(app, method, path, **kw):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        return await ac.request(method, path, **kw)


@pytest.mark.asyncio
async def test_records_request_event():
    app = _make_app()
    await _request(app, "GET", "/something/else")
    events = bus.recent(10)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "request"
    assert ev.method == "GET"
    assert ev.path == "/something/else"
    assert ev.variant is None
    assert ev.status == 200
    assert ev.duration_ms is not None and ev.duration_ms >= 0
    assert ev.request_id and len(ev.request_id) == 12


@pytest.mark.asyncio
async def test_classifies_variants():
    app = _make_app()
    await _request(app, "GET", "/pools/3")
    await _request(app, "POST", "/pools/3/choose-by-context", json={})
    await _request(app, "POST", "/pools/3/choose-by-img", json={})
    variants = [ev.variant for ev in bus.recent(10)]
    assert variants == ["v1", "v2", "v3"]


@pytest.mark.asyncio
async def test_excludes_debug_and_health_paths():
    app = _make_app()
    await _request(app, "GET", "/health")
    await _request(app, "GET", "/debug/anything")
    assert bus.recent(10) == []


@pytest.mark.asyncio
async def test_variant_not_set_for_wrong_method():
    app = _make_app()
    # GET on a POST-only path → would 405 in real app; here just verify variant=None.
    await _request(app, "GET", "/pools/3/choose-by-context")
    [ev] = bus.recent(10)
    assert ev.variant is None
