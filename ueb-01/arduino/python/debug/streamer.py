"""Push the live camera frame to the Web UI debug PiP.

Frames come from the shared :class:`~audience.frame_grabber.FrameGrabber`, which
is the **single** owner of the brick's ``on_detect_all`` callback. (The brick
keeps only one such callback — ``self._handlers[ALL_HANDLERS_KEY]`` — so a second
registration silently clobbers the first; routing every consumer through the one
grabber avoids that and means the preview, the face classifier and the overlay
all share one frame source.) The grabber prefers the freshest detection-callback
frame and falls back to the brick's continuously-updated ``_last_camera_frame``,
so the PiP stays live between detections *and* survives short stalls of either
source — a detection-gated frame alone would blank whenever the scene is empty.

The demographic overlay (per-face age/gender boxes + target group) is drawn by
the frontend from the separate ``audience`` debug event; this streamer only
ships the raw frame.
"""
from __future__ import annotations

import base64
import logging
import threading
import time

from pipeline.context import now_iso

log = logging.getLogger(__name__)


class DebugStreamer:
    def __init__(self, *, ui, frame_provider, throttle_sec: float = 0.4):
        self._ui = ui
        # Callable -> freshest camera frame as raw JPEG bytes (or None). This is
        # FrameGrabber.get; the streamer never touches the detector directly.
        self._frame_provider = frame_provider
        self._throttle = throttle_sec
        self._running = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._frame_provider is None:
            log.warning("debug streamer started without a frame source — nothing to show")
            return
        self._running.set()
        self._thread = threading.Thread(
            target=self._poll_loop, name="DebugStreamer", daemon=True
        )
        self._thread.start()
        log.info("debug streamer started (live preview)")

    def stop(self) -> None:
        self._running.clear()

    def _poll_loop(self) -> None:
        """Emit the live camera frame to the browser at ~1/throttle Hz."""
        while self._running.is_set():
            time.sleep(self._throttle)
            frame = self._frame_provider()
            if not frame:
                continue
            data_url = "data:image/jpeg;base64," + base64.b64encode(frame).decode("ascii")
            self._ui.send_message(
                "debug_detection",
                {"frame": data_url, "ts": now_iso()},
            )
