"""Web UI sink — pushes selector output to the browser via the WebUI Brick."""
from __future__ import annotations

import logging

from sinks.base import ContentSink

log = logging.getLogger(__name__)


class WebUISink(ContentSink):
    def __init__(self, ui):
        self._ui = ui
        # Remember the last content so a browser that connects *after* a
        # selection (the normal case) can still be shown the current content —
        # content_update is otherwise a one-shot broadcast. See resend_last().
        self._last: dict | None = None

    def publish(self, result: dict, context: dict) -> None:
        log.info(
            "publishing content id=%s reasoning=%r",
            result.get("id"),
            result.get("reasoning"),
        )
        payload = {"content": result, "context": context}
        self._last = payload
        self._ui.send_message("content_update", payload)

    def resend_last(self) -> None:
        """Re-broadcast the last published content (no-op if nothing yet).

        Lets late-connecting browser tabs catch up to the current content. The
        frontend ignores a content_update whose id is already shown, so this is
        flicker-free for tabs that already have it.
        """
        if self._last is not None:
            self._ui.send_message("content_update", self._last)

    def publish_error(self, message: str, *, context: dict) -> None:
        log.warning("pipeline error: %s", message)
        self._ui.send_message(
            "pipeline_error",
            {"message": message, "context": context},
        )
