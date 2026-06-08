"""HTTP client for the FastAPI CMS.

Thin wrapper around ``requests`` (sync — App Lab Python code is overwhelmingly
sync; doesn't need an asyncio loop). Surfaces failures via :class:`CMSError`
so callers can decide between degraded behaviour and a hard stop.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from debug.events import NULL_BUS, ms_since

log = logging.getLogger(__name__)

_TIMEOUT_SEC = 10.0


class CMSError(RuntimeError):
    """Raised when the CMS can't be reached or returned an unexpected payload."""


class CMSClient:
    def __init__(self, *, base_url: str, bus=None):
        self._base = base_url.rstrip("/")
        self._bus = bus or NULL_BUS

    def get_pool(self, pool_id: int) -> dict:
        """Variant 1 fetch — returns the full pool with all contents inline."""
        return self._get(f"/pools/{pool_id}")

    def choose_by_context(self, pool_id: int, context: dict) -> dict:
        """Variant 2 — let the CMS pick using the open-shaped context dict."""
        return self._post_json(f"/pools/{pool_id}/choose-by-context", context)

    def choose_by_img(
        self,
        pool_id: int,
        *,
        image_bytes: bytes,
        mime_type: str,
        context: dict | None = None,
    ) -> dict:
        """Variant 3 — upload an image + optional context, get a chosen content."""
        files = {"image": ("frame.jpg", image_bytes, mime_type)}
        data: dict[str, Any] = {}
        if context is not None:
            import json
            data["context"] = json.dumps(context)
        return self._post_multipart(f"/pools/{pool_id}/choose-by-img", files=files, data=data)

    def healthy(self) -> bool:
        """Lightweight reachability check for the debug health strip.

        Deliberately *not* routed through ``_send`` so the periodic poll doesn't
        spam the debug event stream with a ``cms`` event every few seconds.
        """
        try:
            r = requests.get(f"{self._base}/health", timeout=3.0)
            return r.status_code < 400
        except requests.RequestException:
            return False

    # --- low-level -----------------------------------------------------------

    def _get(self, path: str) -> dict:
        return self._send("GET", path)

    def _post_json(self, path: str, body: dict) -> dict:
        return self._send("POST", path, json=body)

    def _post_multipart(self, path: str, *, files: dict, data: dict) -> dict:
        return self._send("POST", path, files=files, data=data)

    def _send(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base}{path}"
        t = time.monotonic()
        try:
            r = requests.request(method, url, timeout=_TIMEOUT_SEC, **kwargs)
        except requests.RequestException as e:
            self._bus.emit("cms", op=method, path=path, status="error", dur_ms=ms_since(t), error=str(e))
            raise CMSError(f"{method} {url} failed: {e}") from e
        self._bus.emit("cms", op=method, path=path, status=r.status_code,
                       dur_ms=ms_since(t), bytes=len(r.content or b""))
        return self._unwrap(r, url)

    @staticmethod
    def _unwrap(response, url: str) -> dict:
        if response.status_code >= 400:
            raise CMSError(
                f"{url} returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as e:
            raise CMSError(f"{url} returned non-JSON body") from e
