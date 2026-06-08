"""Ring buffer + sanitizer behaviour for the debug bus."""
from __future__ import annotations

import pytest

from app.config import settings
from app.debug import bus


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._reset_for_tests()
    yield
    bus._reset_for_tests()


def _event(**kw) -> bus.Event:
    kw.setdefault("kind", "request")
    return bus.Event(**kw)


def test_buffer_keeps_only_last_500():
    for i in range(600):
        bus.push(_event(path=f"/p/{i}"))
    items = bus.recent(1000)
    assert len(items) == 500
    assert items[0].path == "/p/100"
    assert items[-1].path == "/p/599"


def test_recent_returns_tail():
    for i in range(20):
        bus.push(_event(path=f"/p/{i}"))
    items = bus.recent(5)
    assert [e.path for e in items] == ["/p/15", "/p/16", "/p/17", "/p/18", "/p/19"]


def test_recent_zero_or_negative_returns_empty():
    bus.push(_event(path="/p/1"))
    assert bus.recent(0) == []
    assert bus.recent(-1) == []


def test_sanitize_scrubs_mistral_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-secret-123")
    bus.push(
        bus.Event(
            kind="selection",
            variant="v2",
            system_prompt="hello sk-secret-123 world",
            user_prompt="no key here",
            raw_response="also sk-secret-123",
        )
    )
    [ev] = bus.recent(10)
    assert "sk-secret-123" not in (ev.system_prompt or "")
    assert "***" in (ev.system_prompt or "")
    assert "***" in (ev.raw_response or "")
    assert ev.user_prompt == "no key here"


def test_sanitize_noop_when_key_absent(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    bus.push(bus.Event(kind="selection", variant="v2", system_prompt="hello"))
    [ev] = bus.recent(10)
    assert ev.system_prompt == "hello"


def test_sanitize_only_affects_selection_events(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-x")
    # request events with the key shouldn't be touched (path can't contain it
    # in practice, but the sanitizer should leave non-selection fields alone).
    bus.push(bus.Event(kind="request", path="/sk-x/here"))
    [ev] = bus.recent(10)
    assert ev.path == "/sk-x/here"
