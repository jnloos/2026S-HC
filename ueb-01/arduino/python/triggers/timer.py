"""Time-based trigger — fires every N seconds in a background thread."""
from __future__ import annotations

import logging
import threading

from pipeline.context import now_iso
from triggers.base import OnFire, TriggerStrategy

log = logging.getLogger(__name__)


class TimerTrigger(TriggerStrategy):
    def __init__(self, *, interval_sec: float):
        if interval_sec <= 0:
            raise ValueError("interval_sec must be positive")
        self._interval = interval_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_fire: OnFire) -> None:
        if self._thread is not None:
            raise RuntimeError("TimerTrigger already started")

        def _loop():
            log.info("timer trigger started (every %.1fs)", self._interval)
            # Fire once immediately so the screen has content even before the
            # first interval elapses.
            on_fire({"type": "timer", "reason": "initial", "ts": now_iso()})
            while not self._stop.wait(self._interval):
                on_fire({
                    "type": "timer",
                    "reason": f"every {self._interval:g}s",
                    "ts": now_iso(),
                })

        self._thread = threading.Thread(target=_loop, name="digsig-timer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
