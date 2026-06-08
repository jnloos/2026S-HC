"""Variant 2 — hybrid: local vision, cloud (Claude) selection.

Sends the open-shaped context dict to ``POST /pools/{id}/choose-by-context``
and trusts the CMS-side selection. The image stays on the board (only the
audience signal / context travels), which is what makes this the "hybrid"
variant. Emits the same ``selection`` debug event as V1 so the debug window
renders it identically.
"""
from __future__ import annotations

import logging
import time

from cms.client import CMSClient, CMSError
from debug.events import NULL_BUS, ms_since
from pickers.base import ContentSelector, SelectorError, result_from_cms

log = logging.getLogger(__name__)


class HybridSelector(ContentSelector):
    def __init__(self, *, cms: CMSClient, pool_id: int, bus=None):
        self._cms = cms
        self._pool_id = pool_id
        self._bus = bus or NULL_BUS

    def select(self, context: dict) -> dict:
        t = time.monotonic()
        try:
            result = self._cms.choose_by_context(self._pool_id, context)
        except CMSError as e:
            self._bus.emit(
                "selection", variant="v2", pool_id=self._pool_id, chosen_id=None,
                reasoning="", inference_ms=ms_since(t), error=str(e),
            )
            raise SelectorError(f"hybrid (V2) selection failed: {e}") from e

        chosen = result_from_cms(result, "v2")
        self._bus.emit(
            "selection", variant="v2", pool_id=self._pool_id,
            chosen_id=chosen["id"], reasoning=chosen["reasoning"],
            inference_ms=ms_since(t),
        )
        log.info("hybrid (V2) chose id=%s", chosen["id"])
        return chosen
