"""In-memory event bus for the debug UI.

Events live in a bounded ring buffer; SSE subscribers receive new events
through per-connection queues. Nothing is persisted — restart wipes history.
"""
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import settings

# Set by the debug middleware so service-layer hooks can correlate their
# events with the HTTP request that triggered them.
request_id_var: ContextVar[str | None] = ContextVar("debug_request_id", default=None)

_BUFFER_SIZE = 500
_buffer: deque[Event] = deque(maxlen=_BUFFER_SIZE)
_subscribers: set[asyncio.Queue[Event]] = set()


class ImageMeta(BaseModel):
    hash: str
    mime: str
    size_bytes: int


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: Literal["request", "selection"]

    # request-event fields
    method: str | None = None
    path: str | None = None
    variant: Literal["v1", "v2", "v3"] | None = None
    status: int | None = None
    duration_ms: float | None = None

    # selection-event fields
    system_prompt: str | None = None
    user_prompt: str | None = None
    raw_response: str | None = None
    chosen_id: int | None = None
    reasoning: str | None = None
    image_meta: ImageMeta | None = None
    error: str | None = None


def _sanitize(text: str | None) -> str | None:
    """Defensive scrub: replace the Anthropic key if it accidentally leaked into a string field."""
    if text is None:
        return None
    key = settings.anthropic_api_key
    if key and key in text:
        return text.replace(key, "***")
    return text


def _sanitize_event(event: Event) -> Event:
    if event.kind != "selection":
        return event
    return event.model_copy(
        update={
            "system_prompt": _sanitize(event.system_prompt),
            "user_prompt": _sanitize(event.user_prompt),
            "raw_response": _sanitize(event.raw_response),
            "reasoning": _sanitize(event.reasoning),
            "error": _sanitize(event.error),
        }
    )


def push(event: Event) -> None:
    """Append to the buffer and broadcast to all SSE subscribers."""
    event = _sanitize_event(event)
    _buffer.append(event)
    for queue in _subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Slow subscriber — drop rather than block the hot path.
            pass


def recent(limit: int = 100) -> list[Event]:
    """Return the most recent events, oldest first."""
    if limit <= 0:
        return []
    items = list(_buffer)
    return items[-limit:]


async def subscribe() -> AsyncIterator[Event]:
    """Yield events as they arrive. Caller cancels to unsubscribe."""
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=64)
    _subscribers.add(queue)
    try:
        while True:
            yield await queue.get()
    finally:
        _subscribers.discard(queue)


def _reset_for_tests() -> None:
    """Wipe buffer and subscribers — test-only helper."""
    _buffer.clear()
    _subscribers.clear()
