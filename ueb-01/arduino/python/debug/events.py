"""Structured debug event channel for the Arduino client.

Mirrors the API's ``app/debug/bus.py`` idea: a single emitter that pushes
structured events to the browser over the Web UI websocket, so the debug
window can show *what the pipeline is doing* — trigger fires, per-stage
latency, the selector's prompt/response, CMS calls, health and logs.

Everything funnels through :class:`DebugBus`. When ``enabled`` is false the
emitter is a no-op, so production paths pay nothing and we can inject a bus
unconditionally at the call sites.

Browser-facing event shape::

    {"seq": <int>, "kind": <str>, "ts": <iso8601>, ...fields}

All events are sent on the single ``debug_event`` Web UI message; the frontend
routes on ``kind``.
"""
from __future__ import annotations

import logging
import threading
import time

from pipeline.context import now_iso

log = logging.getLogger(__name__)


def ms_since(t0: float) -> float:
    """Milliseconds elapsed since a ``time.monotonic()`` reading, 1-dp."""
    return round((time.monotonic() - t0) * 1000, 1)


class DebugBus:
    """Pushes structured events to the Web UI. No-op when disabled."""

    def __init__(self, ui=None, *, enabled: bool = False):
        self._ui = ui
        self._enabled = bool(enabled and ui is not None)
        self._seq = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(self, kind: str, **fields) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._seq += 1
            seq = self._seq
        try:
            self._ui.send_message("debug_event", {"seq": seq, "kind": kind, "ts": now_iso(), **fields})
        except Exception:  # noqa: BLE001 — debug must never break the pipeline
            # Log at debug level so a failed emit can't feed the log-forwarding
            # handler and cause a loop.
            log.debug("debug emit failed", exc_info=True)


# Shared disabled instance for call sites that receive ``bus=None``.
NULL_BUS = DebugBus(enabled=False)


class BusLogHandler(logging.Handler):
    """Forwards WARNING+ log records into the debug window as ``log`` events.

    A thread-local re-entrancy guard prevents a log emitted *while emitting*
    (e.g. from the websocket layer) from being forwarded again and looping.
    """

    def __init__(self, bus: DebugBus, level: int = logging.WARNING):
        super().__init__(level=level)
        self._bus = bus
        self._guard = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._guard, "busy", False):
            return
        self._guard.busy = True
        try:
            self._bus.emit(
                "log",
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._guard.busy = False


class HealthReporter(threading.Thread):
    """Periodically emits a ``health`` snapshot (CMS reachability + readiness).

    Liveness of the LLM/detector/camera is mostly driven by the live event
    stream on the frontend; this thread keeps the CMS dot honest while idle and
    re-broadcasts the static config snapshot so a late-connecting browser tab
    still gets it.
    """

    def __init__(self, *, bus: DebugBus, cms, config: dict, llm_ok: bool, detector_ok: bool, camera_ok: bool, ui=None, handshake: dict | None = None, interval_sec: float = 5.0):
        super().__init__(name="HealthReporter", daemon=True)
        self._bus = bus
        self._cms = cms
        self._config = config
        self._llm_ok = llm_ok
        self._detector_ok = detector_ok
        self._camera_ok = camera_ok
        self._ui = ui
        self._handshake = handshake
        self._interval = interval_sec
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            # Re-broadcast the one-shot ``config`` handshake every tick. It's
            # sent once at startup, but a browser that connects *later* (the
            # normal case) misses it — and the whole debug UI (PiP, panel,
            # health/detection stream) is gated on it. Re-sending makes a
            # late-joining tab pick it up within one interval. Idempotent.
            if self._ui is not None and self._handshake is not None:
                try:
                    self._ui.send_message("config", self._handshake)
                except Exception:  # noqa: BLE001 — debug must never break the app
                    pass
            cms_ok = False
            try:
                cms_ok = bool(self._cms.healthy())
            except Exception:  # noqa: BLE001
                cms_ok = False
            self._bus.emit(
                "health",
                cms=cms_ok,
                llm=self._llm_ok,
                detector=self._detector_ok,
                camera=self._camera_ok,
                config=self._config,
            )
            self._stop.wait(self._interval)
