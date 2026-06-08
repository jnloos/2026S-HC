"""ASGI middleware that records every non-excluded HTTP request to the debug bus."""
from __future__ import annotations

import re
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.debug import bus

# Paths we never log — debug surfaces (would loop), health probe (noise).
_EXCLUDED_PREFIXES = ("/debug", "/health", "/docs", "/openapi.json", "/redoc")

_V1 = re.compile(r"^/pools/\d+$")
_V2 = re.compile(r"^/pools/\d+/choose-by-context$")
_V3 = re.compile(r"^/pools/\d+/choose-by-img$")


def _classify_variant(method: str, path: str) -> str | None:
    if method == "GET" and _V1.fullmatch(path):
        return "v1"
    if method == "POST" and _V2.fullmatch(path):
        return "v2"
    if method == "POST" and _V3.fullmatch(path):
        return "v3"
    return None


def _is_excluded(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _EXCLUDED_PREFIXES)


class DebugMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_excluded(request.url.path):
            return await call_next(request)

        request_id = uuid4().hex[:12]
        token = bus.request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            bus.push(
                bus.Event(
                    kind="request",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    variant=_classify_variant(request.method, request.url.path),
                    status=status,
                    duration_ms=round(duration_ms, 2),
                )
            )
            bus.request_id_var.reset(token)
