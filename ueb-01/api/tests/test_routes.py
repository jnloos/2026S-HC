"""HTTP route tests. Claude calls are mocked at ``selection._post_chat``."""
import json

import pytest

from app.services import contents as content_service
from app.services import pools as pool_service
from app.services import selection as selection_service


async def _seed(session, *, pool_name="default"):
    pool = await pool_service.create_pool(session, name=pool_name, description="desc")
    sunny = await content_service.add_content(
        session,
        pool_id=pool.id,
        name="sunny",
        html="<h1>Sunny day!</h1>",
        description="for bright days, all audiences",
    )
    rainy = await content_service.add_content(
        session,
        pool_id=pool.id,
        name="rainy",
        html="<h1>Bring an umbrella</h1>",
        description="for rainy weather",
    )
    return pool, sunny, rainy


# --- GET /pools/{id} (Variant 1) -------------------------------------------

async def test_get_pool_returns_contents_inline(client, session):
    pool, sunny, rainy = await _seed(session)

    response = await client.get(f"/pools/{pool.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == pool.id
    assert body["name"] == "default"
    assert body["description"] == "desc"
    by_id = {c["id"]: c for c in body["contents"]}
    assert by_id[sunny.id] == {
        "id": sunny.id,
        "name": "sunny",
        "description": "for bright days, all audiences",
        "html": "<h1>Sunny day!</h1>",
    }
    assert by_id[rainy.id]["html"] == "<h1>Bring an umbrella</h1>"
    assert by_id[rainy.id]["description"] == "for rainy weather"


async def test_get_pool_missing_returns_404(client):
    response = await client.get("/pools/9999")
    assert response.status_code == 404


# --- POST /pools/{id}/choose-by-context (Variant 2) ------------------------

async def test_choose_by_context_returns_choice(client, session, monkeypatch):
    pool, sunny, rainy = await _seed(session)

    async def fake_post_chat(system, user_content):
        return json.dumps({"chosen_id": rainy.id, "reasoning": "wet weather"})

    monkeypatch.setattr(selection_service, "_post_chat", fake_post_chat)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-context",
        json={"audience": {"group": "adult"}, "weather": "rain"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "pool_id": pool.id,
        "chosen_id": rainy.id,
        "name": "rainy",
        "description": "for rainy weather",
        "html": "<h1>Bring an umbrella</h1>",
        "reasoning": "wet weather",
    }


async def test_choose_by_context_prompt_includes_descriptions(client, session, monkeypatch):
    """The whole point of Content.description: it must reach the LLM."""
    pool, _sunny, rainy = await _seed(session)
    seen = {}

    async def capture(system, user_content):
        seen["user"] = user_content
        return json.dumps({"chosen_id": rainy.id, "reasoning": "ok"})

    monkeypatch.setattr(selection_service, "_post_chat", capture)
    response = await client.post(
        f"/pools/{pool.id}/choose-by-context", json={"audience": {"group": "anyone"}}
    )
    assert response.status_code == 200
    assert "for rainy weather" in seen["user"]
    assert "for bright days" in seen["user"]


async def test_choose_by_context_accepts_unknown_keys(client, session, monkeypatch):
    """Unknown context keys must flow into the prompt rather than be rejected."""
    pool, _sunny, rainy = await _seed(session)
    seen = {}

    async def capture(system, user_content):
        seen["user"] = user_content
        return json.dumps({"chosen_id": rainy.id, "reasoning": "ok"})

    monkeypatch.setattr(selection_service, "_post_chat", capture)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-context",
        json={
            "audience": {"group": "kid"},
            "loudness": "high",
            "time_of_day": "evening",
            "extras": {"foo": 1},
        },
    )

    assert response.status_code == 200
    prompt = seen["user"]
    # Every top-level key must be present in the rendered prompt.
    assert "loudness" in prompt
    assert "time_of_day" in prompt
    assert "extras" in prompt
    # Nested data should also be visible.
    assert "kid" in prompt
    assert "evening" in prompt


async def test_choose_by_context_empty_pool_returns_409(client, session):
    pool = await pool_service.create_pool(session, name="empty")
    response = await client.post(
        f"/pools/{pool.id}/choose-by-context", json={"audience": {"group": "adult"}}
    )
    assert response.status_code == 409


async def test_choose_by_context_missing_pool_returns_404(client):
    response = await client.post(
        "/pools/9999/choose-by-context", json={"audience": {"group": "adult"}}
    )
    assert response.status_code == 404


async def test_choose_by_context_invalid_id_returns_502(client, session, monkeypatch):
    pool, sunny, _ = await _seed(session)

    async def bad_post_chat(system, user_content):
        return json.dumps({"chosen_id": 999999, "reasoning": "out of range"})

    monkeypatch.setattr(selection_service, "_post_chat", bad_post_chat)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-context", json={"audience": {"group": "adult"}}
    )
    assert response.status_code == 502
    assert "not in the pool" in response.json()["detail"]


async def test_choose_by_context_malformed_json_returns_502(client, session, monkeypatch):
    pool, _, _ = await _seed(session)

    async def garbage(system, user_content):
        return "this is not json"

    monkeypatch.setattr(selection_service, "_post_chat", garbage)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-context", json={"audience": {"group": "adult"}}
    )
    assert response.status_code == 502


# --- POST /pools/{id}/choose-by-img (Variant 3) ----------------------------

async def test_choose_by_img_returns_choice(client, session, monkeypatch):
    pool, sunny, _ = await _seed(session)

    async def fake_post_chat(system, user_content):
        # Verify the prompt includes the image as a Claude vision block.
        assert isinstance(user_content, list)
        assert any(b.get("type") == "image" for b in user_content)
        return json.dumps({"chosen_id": sunny.id, "reasoning": "bright vibes"})

    monkeypatch.setattr(selection_service, "_post_chat", fake_post_chat)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-img",
        files={"image": ("frame.jpg", b"\xff\xd8\xff fake jpeg bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chosen_id"] == sunny.id
    assert body["reasoning"] == "bright vibes"
    assert body["html"] == "<h1>Sunny day!</h1>"


async def test_choose_by_img_empty_image_returns_400(client, session):
    pool, _, _ = await _seed(session)
    response = await client.post(
        f"/pools/{pool.id}/choose-by-img",
        files={"image": ("frame.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400


async def test_choose_by_img_with_optional_context_form_field(client, session, monkeypatch):
    """Variant 3 takes an optional JSON-encoded context — analogous to V2."""
    pool, sunny, _ = await _seed(session)
    seen_text = {}

    async def capturing_post_chat(system, user_content):
        for block in user_content:
            if block.get("type") == "text":
                seen_text["text"] = block["text"]
        return json.dumps({"chosen_id": sunny.id, "reasoning": "ok"})

    monkeypatch.setattr(selection_service, "_post_chat", capturing_post_chat)

    response = await client.post(
        f"/pools/{pool.id}/choose-by-img",
        files={"image": ("frame.jpg", b"\xff\xd8\xff bytes", "image/jpeg")},
        data={"context": json.dumps({"audience": {"group": "kid"}, "weather": "snowing"})},
    )

    assert response.status_code == 200
    text = seen_text["text"]
    assert "audience" in text
    assert "kid" in text
    assert "snowing" in text


async def test_choose_by_img_with_invalid_context_returns_400(client, session):
    pool, _, _ = await _seed(session)
    response = await client.post(
        f"/pools/{pool.id}/choose-by-img",
        files={"image": ("frame.jpg", b"\xff\xd8\xff bytes", "image/jpeg")},
        data={"context": "not-json-at-all"},
    )
    assert response.status_code == 400


async def test_choose_by_img_with_non_object_context_returns_400(client, session):
    pool, _, _ = await _seed(session)
    response = await client.post(
        f"/pools/{pool.id}/choose-by-img",
        files={"image": ("frame.jpg", b"\xff\xd8\xff bytes", "image/jpeg")},
        data={"context": json.dumps(["a", "b"])},
    )
    assert response.status_code == 400
