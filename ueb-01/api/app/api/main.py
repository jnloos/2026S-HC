"""FastAPI application factory / ASGI entry point.

Run locally:
    cd api
    pip install -e .
    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

Interactive docs at http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routers import contents, pools
from app.config import settings
from app.storage import ensure_dirs


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ensure storage dirs exist. The DB schema is managed by Alembic migrations
    # (run `digsig db upgrade`), not auto-created on startup.
    ensure_dirs()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(pools.router)
app.include_router(contents.router)

if settings.debug_ui_enabled:
    from app.debug.middleware import DebugMiddleware
    from app.debug.router import WEB_DIR, router as debug_router

    app.add_middleware(DebugMiddleware)
    # Register dynamic routes first so /debug/static doesn't shadow them.
    app.include_router(debug_router)
    static_dir = WEB_DIR / "static"
    if static_dir.exists():
        app.mount("/debug/static", StaticFiles(directory=static_dir), name="debug-static")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
