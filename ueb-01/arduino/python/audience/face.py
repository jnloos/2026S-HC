"""Camera-based audience classifier backed by the in-process inference pipeline.

Grabs the current camera frame (via a zero-arg ``frame_provider`` callable,
typically :meth:`audience.frame_grabber.FrameGrabber.get`) and classifies it
directly with an :class:`audience.inference.AudiencePipeline` — no sidecar, no
HTTP. The returned dict follows the audience contract::

    {"people_count": int, "faces": [...], "target_group": str, "source": str}

Like every :class:`~audience.base.AudienceClassifier`, ``classify()`` **never
raises** — the pipeline wraps it in try/except, but we still degrade to an
``"unknown"`` dict on any failure so a wedged model can't stall the loop.

This feeds the pipeline's content *selection*. The debug-preview demographic
overlay is produced separately (and at a higher rate) by
:class:`debug.audience_overlay.AudienceOverlayWorker`, sharing the same
pipeline instance.
"""
from __future__ import annotations

import logging

from audience.base import AudienceClassifier
from debug.events import NULL_BUS

log = logging.getLogger(__name__)


class FaceAudienceClassifier(AudienceClassifier):
    def __init__(self, *, pipeline, frame_provider, bus=None):
        self._pipeline = pipeline
        self._frame_provider = frame_provider
        self._bus = bus or NULL_BUS

    def classify(self) -> dict:
        frame = self._frame_provider()
        if frame is None:
            log.info("face classifier: no camera frame available")
            self._bus.emit("face", op="classify", status="no-frame")
            return {"people_count": 0, "faces": [], "target_group": "unknown", "source": "face-no-frame"}
        try:
            result = self._pipeline.classify(frame)
        except Exception as e:  # noqa: BLE001 — classifier must never raise
            log.exception("face classifier inference failed")
            self._bus.emit("face", op="classify", status="error", error=str(e))
            return {"people_count": 0, "faces": [], "target_group": "unknown", "source": "face-error"}
        self._bus.emit(
            "face",
            op="classify",
            status="ok",
            people_count=result.get("people_count"),
            target_group=result.get("target_group"),
        )
        return result
