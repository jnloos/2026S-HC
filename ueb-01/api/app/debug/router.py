"""HTTP surface for the debug UI: index, SSE stream, recent backfill."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.config import BASE_DIR, settings
from app.debug import bus

# Repo-root/web — sibling of api/ and arduino/.
WEB_DIR: Path = BASE_DIR.parent / "web"

router = APIRouter(prefix="/debug", tags=["debug"])


def _require_token(
    request: Request,
    token: str | None = Query(default=None),
) -> None:
    """Optional bearer-style auth. No-op if DEBUG_TOKEN is unset (lab/LAN mode)."""
    expected = settings.debug_token
    if not expected:
        return
    if token == expected:
        return
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and auth[len("Bearer ") :] == expected:
        return
    raise HTTPException(status_code=401, detail="debug token required")


@router.get("", include_in_schema=False)
async def index(_: None = Depends(_require_token)) -> FileResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail=f"web/index.html missing at {index_path}")
    return FileResponse(index_path)


@router.get("/recent")
async def recent(
    limit: int = Query(default=100, ge=1, le=500),
    _: None = Depends(_require_token),
) -> list[bus.Event]:
    return bus.recent(limit)


@router.get("/stream")
async def stream(_: None = Depends(_require_token)) -> StreamingResponse:
    """Server-Sent Events stream of new debug events.

    A 15-second keepalive comment keeps idle connections alive through proxies.
    """
    async def event_source():
        subscription = bus.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(subscription.__anext__(), timeout=15.0)
                    yield f"data: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except StopAsyncIteration:
                    break
        finally:
            await subscription.aclose()

    return StreamingResponse(event_source(), media_type="text/event-stream")
