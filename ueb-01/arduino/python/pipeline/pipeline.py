"""Pipeline orchestrator.

Wires the three strategy slots together:
    trigger ─► classifier ─► selector ─► sink

A trigger calls :meth:`Pipeline.run_once` with an initial context dict (carrying
trigger-side metadata). The pipeline asks the classifier for audience info,
merges it in, then asks the selector for a content choice and publishes the
result via the sink. Errors at any stage are caught and surfaced via the sink
so the UI can show a degraded state instead of going silent.

When a :class:`~debug.events.DebugBus` is injected (debug mode), each cycle
emits a ``run_started`` event, a per-stage ``stage`` event with ``dur_ms``, and
a ``run_done`` event with the total — so the debug window can draw a timeline
showing where time goes (inference-dominated on edge, network on cloud).
"""
from __future__ import annotations

import logging
import time

from debug.events import NULL_BUS, ms_since

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, *, classifier, selector, sink, bus=None):
        self._classifier = classifier
        self._selector = selector
        self._sink = sink
        self._bus = bus or NULL_BUS
        self._run_seq = 0

    def run_once(self, initial_ctx: dict) -> None:
        """Run one full pipeline cycle. Never raises — errors go to the sink."""
        self._run_seq += 1
        run = self._run_seq
        t_run = time.monotonic()
        self._bus.emit("run_started", run=run, trigger=initial_ctx.get("trigger"))

        t = time.monotonic()
        try:
            audience = self._classifier.classify()
        except Exception as e:  # noqa: BLE001 — classifier failure must not kill the loop
            log.exception("classifier failed")
            self._bus.emit("stage", run=run, stage="classify", status="error", dur_ms=ms_since(t), error=str(e))
            self._bus.emit("run_done", run=run, status="error", total_ms=ms_since(t_run))
            self._sink.publish_error(f"classifier failed: {e}", context=initial_ctx)
            return
        self._bus.emit("stage", run=run, stage="classify", status="done", dur_ms=ms_since(t), audience=audience)

        context: dict = {**initial_ctx, "audience": audience}

        t = time.monotonic()
        try:
            result = self._selector.select(context)
        except Exception as e:  # noqa: BLE001
            log.exception("selector failed")
            self._bus.emit("stage", run=run, stage="select", status="error", dur_ms=ms_since(t), error=str(e))
            self._bus.emit("run_done", run=run, status="error", total_ms=ms_since(t_run))
            self._sink.publish_error(f"selector failed: {e}", context=context)
            return
        self._bus.emit("stage", run=run, stage="select", status="done", dur_ms=ms_since(t),
                       chosen_id=result.get("id"), variant=result.get("variant"))

        t = time.monotonic()
        try:
            self._sink.publish(result, context)
            self._bus.emit("stage", run=run, stage="publish", status="done", dur_ms=ms_since(t))
        except Exception:  # noqa: BLE001
            log.exception("sink publish failed")
            self._bus.emit("stage", run=run, stage="publish", status="error", dur_ms=ms_since(t))
            # Nothing more we can do — sink itself is broken.

        self._bus.emit("run_done", run=run, status="ok", total_ms=ms_since(t_run), chosen_id=result.get("id"))
        # Uniform stdout marker for every variant — lets external tooling (e.g.
        # cli/verify-pipelines.sh) confirm a full cycle completed from the logs.
        log.info(
            "PIPELINE_CYCLE_OK run=%s variant=%s id=%s total_ms=%s",
            run, result.get("variant"), result.get("id"), ms_since(t_run),
        )
