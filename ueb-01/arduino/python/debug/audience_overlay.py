"""Independent, high-rate audience-overlay worker for the debug preview.

Decoupled from the pipeline: a background thread classifies the live camera
frame in-process every ``interval_sec`` and emits an ``audience``
debug event (per-face age/gender boxes + scene target group), so the Web UI
preview tracks the viewer responsively — regardless of the pipeline's trigger
or selector variant. This is a debug-only visualization; it does **not** feed
content selection (that's the pipeline's own classify step in
:mod:`audience.face`).

No-op when debug is off. Never crashes the app — every tick is guarded.
"""
from __future__ import annotations

import logging
import threading
import time

from debug.events import NULL_BUS

log = logging.getLogger(__name__)


class AudienceOverlayWorker:
    def __init__(self, *, bus, frame_provider, pipeline, interval_sec: float = 1.0):
        self._bus = bus or NULL_BUS
        self._frame_provider = frame_provider
        self._pipeline = pipeline
        self._interval = max(0.1, float(interval_sec))
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        # Tracks whether we've been emitting frames, so we push exactly one
        # "clear" event when the camera stops delivering frames.
        self._active = False

    def start(self) -> None:
        if not getattr(self._bus, "enabled", False):
            log.info("audience overlay worker disabled (debug off)")
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="AudienceOverlay", daemon=True)
        self._thread.start()
        log.info("audience overlay worker started (every %.2fs)", self._interval)

    def stop(self) -> None:
        self._running.clear()

    def _loop(self) -> None:
        while self._running.is_set():
            time.sleep(self._interval)
            try:
                self._tick()
            except Exception:  # noqa: BLE001 — overlay must never crash the app
                log.debug("audience overlay tick failed", exc_info=True)

    def _tick(self) -> None:
        frame = self._frame_provider()
        if frame is None:
            if self._active:
                self._active = False
                self._emit({"faces": [], "target_group": "unknown", "people_count": 0}, None)
            return
        try:
            result = self._pipeline.classify(frame)
        except Exception as e:  # noqa: BLE001 — an inference hiccup must not stop the worker
            log.debug("overlay classify failed: %s", e)
            return
        self._active = True
        self._emit(result, frame)

    def _emit(self, result: dict, frame) -> None:
        w, h = _jpeg_size(frame) if frame else (0, 0)
        self._bus.emit(
            "audience",
            faces=result.get("faces", []),
            target_group=result.get("target_group", "unknown"),
            people_count=result.get("people_count", 0),
            frame_w=w,
            frame_h=h,
        )


# Standalone JPEG markers (no length field) we skip while scanning.
_JPEG_STANDALONE = {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9}
# Start-of-frame markers that carry the image dimensions.
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(data: bytes) -> tuple[int, int]:
    """Return ``(width, height)`` of a JPEG from its bytes, or ``(0, 0)`` if unparseable.

    Dependency-free SOF-marker scan — the board app can't assume Pillow/cv2. The
    frontend uses these to normalize the (classified-frame) face boxes against a
    possibly-downscaled preview frame.
    """
    try:
        if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
            return (0, 0)
        i, n = 2, len(data)
        while i + 1 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in _JPEG_STANDALONE or marker == 0xFF:
                continue
            if i + 1 >= n:
                break
            seg_len = (data[i] << 8) | data[i + 1]
            if marker in _JPEG_SOF and i + 6 < n:
                h = (data[i + 3] << 8) | data[i + 4]
                w = (data[i + 5] << 8) | data[i + 6]
                return (w, h)
            i += seg_len
        return (0, 0)
    except Exception:  # noqa: BLE001 — overlay dims are best-effort, never fatal
        return (0, 0)
