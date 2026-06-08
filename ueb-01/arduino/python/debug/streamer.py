"""Push the live camera frame to the Web UI debug PiP.

The ``VideoObjectDetection`` brick, when constructed with ``camera_preview=True``,
continuously keeps the most recent camera frame as a base64 data-URL in its
``_last_camera_frame`` attribute (refreshed by ``camera-preview`` websocket
messages **even when nothing is detected**). We poll that on a background thread
for a video-chat-style continuous self-view — a detection-gated frame alone
would leave the preview blank whenever the scene is empty.

The demographic overlay (per-face age/gender boxes + target group) is drawn by
the frontend from the separate ``audience`` debug event; this streamer only
ships the raw frame. (Earlier versions also forwarded the brick's YoloX
person-detection boxes here, but the overlay no longer uses them.)
"""
from __future__ import annotations

import base64
import logging
import threading
import time

from pipeline.context import now_iso

log = logging.getLogger(__name__)


class DebugStreamer:
    def __init__(self, *, ui, detector, throttle_sec: float = 0.4):
        self._ui = ui
        self._detector = detector
        self._throttle = throttle_sec
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # Frame captured via the detection callback, base64 data-URL. Used as a
        # fallback when the brick doesn't expose the continuous preview frame.
        self._cb_frame: str | None = None

    def start(self) -> None:
        if self._detector is None:
            log.warning("debug streamer started without a detector — nothing to show")
            return
        if not hasattr(self._detector, "on_detect_all"):
            log.warning("detector has no on_detect_all; debug stream disabled")
            return

        # The brick validates the callback with a function-type check (it raises
        # TypeError on bound methods) and inspects the signature: a param named
        # `frame` makes it pass the raw JPEG frame. Register a plain wrapper with
        # that exact parameter name; the detection payload itself is unused.
        def _on_all(detections, frame=None):
            if not frame:
                return
            data_url = "data:image/jpeg;base64," + base64.b64encode(frame).decode("ascii")
            with self._lock:
                self._cb_frame = data_url

        self._detector.on_detect_all(_on_all)

        self._running.set()
        self._thread = threading.Thread(
            target=self._poll_loop, name="DebugStreamer", daemon=True
        )
        self._thread.start()
        log.info("debug streamer attached to detector (live preview)")

    def stop(self) -> None:
        self._running.clear()

    def _poll_loop(self) -> None:
        """Emit the live camera frame to the browser at ~1/throttle Hz."""
        while self._running.is_set():
            time.sleep(self._throttle)
            # Prefer the brick's continuously-updated preview frame so the PiP
            # stays live between detections; fall back to the last callback frame.
            with self._lock:
                cb_frame = self._cb_frame
            frame = getattr(self._detector, "_last_camera_frame", None) or cb_frame
            if frame is None:
                continue
            self._ui.send_message(
                "debug_detection",
                {"frame": frame, "ts": now_iso()},
            )
