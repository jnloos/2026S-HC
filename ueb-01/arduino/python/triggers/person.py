"""Person-detected trigger — fires when a person/face shows up in the video feed.

Uses the `arduino:video_object_detection` Brick. We register a callback for
the "person" label; debounce prevents the pipeline from firing on every frame
while someone is standing in front of the screen.
"""
from __future__ import annotations

import logging
import threading
import time

from pipeline.context import now_iso
from triggers.base import OnFire, TriggerStrategy

log = logging.getLogger(__name__)

# Labels we'd consider "audience present". `person` is the canonical
# COCO-style label; some detection models emit `face` instead, so we listen
# for both and dedupe via debounce.
_PRESENCE_LABELS = ("person", "face")


class PersonTrigger(TriggerStrategy):
    def __init__(self, detector, *, debounce_sec: float):
        if detector is None:
            raise ValueError("PersonTrigger requires a video detector")
        if debounce_sec < 0:
            raise ValueError("debounce_sec must be >= 0")
        self._detector = detector
        self._debounce = debounce_sec
        self._lock = threading.Lock()
        self._last_fire_ts: float = 0.0
        self._on_fire: OnFire | None = None

    def start(self, on_fire: OnFire) -> None:
        if self._on_fire is not None:
            raise RuntimeError("PersonTrigger already started")
        self._on_fire = on_fire
        for label in _PRESENCE_LABELS:
            self._detector.on_detect(label, self._handle_detection(label))
        log.info(
            "person trigger started (labels=%s, debounce=%.1fs)",
            list(_PRESENCE_LABELS),
            self._debounce,
        )

    def stop(self) -> None:
        # VideoObjectDetection in the App Lab examples doesn't expose an
        # off-handler; the App lifecycle takes care of teardown on App.run() exit.
        self._on_fire = None

    def _handle_detection(self, label: str):
        def _cb(*args, **kwargs):  # noqa: ARG001 — brick passes detection metadata; we don't need it here
            now = time.monotonic()
            with self._lock:
                if now - self._last_fire_ts < self._debounce:
                    return
                self._last_fire_ts = now
            if self._on_fire is None:
                return
            self._on_fire({
                "type": "person",
                "reason": f"{label} detected",
                "ts": now_iso(),
            })
        return _cb
