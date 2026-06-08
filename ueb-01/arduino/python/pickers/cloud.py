"""Variant 3 — cloud-only: raw image + optional context to the CMS.

Claude does both vision and selection. The Arduino sends a JPEG plus an
optional JSON-string context to ``POST /pools/{id}/choose-by-img``. Emits the
same ``selection`` debug event as the other variants.
"""
from __future__ import annotations

import logging
import time

from cms.client import CMSClient, CMSError
from debug.events import NULL_BUS, ms_since
from pickers.base import ContentSelector, SelectorError, result_from_cms

log = logging.getLogger(__name__)


class CloudSelector(ContentSelector):
    def __init__(self, *, cms: CMSClient, pool_id: int, frame_provider, bus=None):
        """``frame_provider`` returns ``(image_bytes, mime_type)`` on demand."""
        self._cms = cms
        self._pool_id = pool_id
        self._frame_provider = frame_provider
        self._bus = bus or NULL_BUS

    def select(self, context: dict) -> dict:
        t = time.monotonic()
        image_bytes, mime = self._frame_provider()
        if not image_bytes:
            self._bus.emit(
                "selection", variant="v3", pool_id=self._pool_id, chosen_id=None,
                reasoning="", inference_ms=ms_since(t), error="no camera frame",
            )
            raise SelectorError("CloudSelector (V3) has no camera frame to send")

        try:
            result = self._cms.choose_by_img(
                self._pool_id, image_bytes=image_bytes,
                mime_type=mime or "image/jpeg", context=context,
            )
        except CMSError as e:
            self._bus.emit(
                "selection", variant="v3", pool_id=self._pool_id, chosen_id=None,
                reasoning="", inference_ms=ms_since(t), error=str(e),
            )
            raise SelectorError(f"cloud (V3) selection failed: {e}") from e

        chosen = result_from_cms(result, "v3")
        self._bus.emit(
            "selection", variant="v3", pool_id=self._pool_id,
            chosen_id=chosen["id"], reasoning=chosen["reasoning"],
            inference_ms=ms_since(t),
        )
        log.info("cloud (V3) chose id=%s", chosen["id"])
        return chosen
