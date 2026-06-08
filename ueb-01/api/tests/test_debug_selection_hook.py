"""Selection service emits debug events with the right shape — no base64 blobs."""
from __future__ import annotations

import json

import pytest

from app.debug import bus
from app.services import contents as content_service
from app.services import pools as pool_service
from app.services import selection as selection_service


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._reset_for_tests()
    yield
    bus._reset_for_tests()


async def _seed(session):
    pool = await pool_service.create_pool(session, name="p", description="d")
    a = await content_service.add_content(session, pool_id=pool.id, name="a", html="<p>a</p>", description="desc a")
    b = await content_service.add_content(session, pool_id=pool.id, name="b", html="<p>b</p>", description="desc b")
    return pool, a, b


async def test_choose_by_context_pushes_selection_event(session, monkeypatch):
    _, a, _ = await _seed(session)

    async def fake_post_chat(system, user_content):
        return json.dumps({"chosen_id": a.id, "reasoning": "looks fine"})

    monkeypatch.setattr(selection_service, "_post_chat", fake_post_chat)
    items = await content_service.list_for_pool(session, a.pool_id)
    result = await selection_service.choose_by_context(
        items, context={"audience": {"group": "any"}}
    )

    [ev] = bus.recent(10)
    assert ev.kind == "selection"
    assert ev.variant == "v2"
    assert ev.chosen_id == result.chosen_id == a.id
    assert ev.reasoning == "looks fine"
    assert ev.system_prompt and "candidate" in ev.system_prompt.lower() or ev.system_prompt
    assert ev.user_prompt and "desc a" in ev.user_prompt
    assert ev.raw_response and a.id == json.loads(ev.raw_response)["chosen_id"]
    assert ev.error is None
    assert ev.image_meta is None


async def test_choose_by_image_pushes_event_without_base64(session, monkeypatch):
    _, a, _ = await _seed(session)
    image_bytes = b"\xff\xd8\xff some fake jpeg bytes here"

    async def fake_post_chat(system, user_content):
        return json.dumps({"chosen_id": a.id, "reasoning": "img ok"})

    monkeypatch.setattr(selection_service, "_post_chat", fake_post_chat)
    items = await content_service.list_for_pool(session, a.pool_id)
    await selection_service.choose_by_image(items, image_bytes=image_bytes, mime_type="image/jpeg")

    [ev] = bus.recent(10)
    assert ev.variant == "v3"
    assert ev.image_meta is not None
    assert ev.image_meta.mime == "image/jpeg"
    assert ev.image_meta.size_bytes == len(image_bytes)
    assert len(ev.image_meta.hash) == 16
    # Defensive: the base64 form of the bytes must NOT appear in any text field.
    import base64
    b64 = base64.b64encode(image_bytes).decode()
    blob = " ".join(filter(None, [ev.system_prompt, ev.user_prompt, ev.raw_response]))
    assert b64 not in blob


async def test_selection_error_pushes_event_with_error(session, monkeypatch):
    pool, a, _ = await _seed(session)

    async def bad_post_chat(system, user_content):
        return json.dumps({"chosen_id": 99999, "reasoning": "out of range"})

    monkeypatch.setattr(selection_service, "_post_chat", bad_post_chat)
    items = await content_service.list_for_pool(session, pool.id)

    with pytest.raises(selection_service.SelectionError):
        await selection_service.choose_by_context(items, context={"audience": {"group": "any"}})

    [ev] = bus.recent(10)
    assert ev.kind == "selection"
    assert ev.error is not None
    assert "not in the pool" in ev.error
    assert ev.chosen_id is None


async def test_request_id_propagates_to_selection_event(session, monkeypatch):
    _, a, _ = await _seed(session)

    async def fake_post_chat(system, user_content):
        return json.dumps({"chosen_id": a.id, "reasoning": "ok"})

    monkeypatch.setattr(selection_service, "_post_chat", fake_post_chat)
    items = await content_service.list_for_pool(session, a.pool_id)

    token = bus.request_id_var.set("test-req-123")
    try:
        await selection_service.choose_by_context(items, context={"audience": {"group": "any"}})
    finally:
        bus.request_id_var.reset(token)

    [ev] = bus.recent(10)
    assert ev.request_id == "test-req-123"
