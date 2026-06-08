"""On-demand access to the most recent camera frame as raw JPEG bytes.

The face classifier needs a frame *when it runs* (driven by a trigger), not a
continuous stream. The ``VideoObjectDetection`` brick exposes frames two ways:

* The ``on_detect_all`` callback receives a ``frame`` keyword (raw JPEG bytes)
  whenever something is detected — see :mod:`debug.streamer` for the
  authoritative registration pattern (a plain function with a ``frame`` param,
  *not* a bound method).
* It continuously keeps the latest frame as a base64 data-URL string in its
  private ``_last_camera_frame`` attribute (refreshed even when nothing is
  detected, when ``camera_preview=True``).

:class:`FrameGrabber` caches the freshest callback frame and falls back to
decoding ``_last_camera_frame`` when the cache is stale. The brick internals are
private, so every access is defensive — ``get()`` never raises.
"""
from __future__ import annotations

import base64
import logging
import threading
import time

log = logging.getLogger(__name__)

# How long a callback-supplied frame stays "fresh" before we fall back to the
# brick's continuously-updated preview frame. Detections arrive on their own
# cadence; without this the cached frame would go stale after a person leaves.
_FRAME_TTL_SEC = 2.0


class FrameGrabber:
    def __init__(self, detector):
        self._detector = detector
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_ts: float = 0.0
        self._register()

    def _register(self) -> None:
        """Attach the detection callback so we cache the freshest raw frame."""
        detector = self._detector
        if detector is None or not hasattr(detector, "on_detect_all"):
            log.warning("detector has no on_detect_all — frame grabber falls back to preview only")
            return

        # The brick validates the callback as a function (raises on bound
        # methods) and inspects the signature: a param named `frame` makes it
        # pass the raw JPEG. Register a plain wrapper with that exact name.
        def _on_all(detections, frame=None):
            if frame:
                with self._lock:
                    self._frame = frame
                    self._frame_ts = time.monotonic()

        try:
            detector.on_detect_all(_on_all)
        except Exception:  # noqa: BLE001 — never let registration kill startup
            log.warning("could not register frame-grabber callback", exc_info=True)

    def get(self) -> bytes | None:
        """Return the freshest camera frame as raw JPEG bytes, or ``None``.

        Prefers the cached callback frame if it's fresh (< ~2s); otherwise
        decodes the brick's continuously-updated ``_last_camera_frame`` data-URL.
        Never raises — returns ``None`` on any failure.
        """
        try:
            with self._lock:
                frame = self._frame
                fresh = time.monotonic() - self._frame_ts <= _FRAME_TTL_SEC
            if frame is not None and fresh:
                return frame
            return self._decode_preview()
        except Exception:  # noqa: BLE001 — frame access must never break the pipeline
            log.debug("frame grab failed", exc_info=True)
            return None

    def _decode_preview(self) -> bytes | None:
        """Decode the brick's base64 data-URL preview frame to raw JPEG bytes."""
        data_url = getattr(self._detector, "_last_camera_frame", None)
        if not data_url or not isinstance(data_url, str):
            return None
        # Strip an optional ``data:image/...;base64,`` prefix before decoding.
        b64 = data_url
        comma = data_url.find(",")
        if data_url.startswith("data:") and comma != -1:
            b64 = data_url[comma + 1:]
        try:
            return base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            log.debug("preview frame base64 decode failed", exc_info=True)
            return None
