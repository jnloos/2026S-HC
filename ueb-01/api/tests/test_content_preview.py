"""Tests for the browser-preview route GET /contents/{id}."""
from app.services import contents as content_service
from app.services import pools as pool_service


async def test_preview_returns_html_with_snippet(client, session):
    pool = await pool_service.create_pool(session, name="p")
    c = await content_service.add_content(
        session,
        pool_id=pool.id,
        name="hello",
        html="<div class='abc-card'>hi there</div>",
        description="for testing",
    )

    response = await client.get(f"/contents/{c.id}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    body = response.text
    assert "<!doctype html>" in body
    assert f"content #{c.id}" in body
    assert "<div class='abc-card'>hi there</div>" in body
    assert "for testing" in body


async def test_preview_without_description_omits_block(client, session):
    pool = await pool_service.create_pool(session, name="p")
    c = await content_service.add_content(
        session, pool_id=pool.id, name="x", html="<p>x</p>"
    )

    response = await client.get(f"/contents/{c.id}")
    assert response.status_code == 200
    # CSS rule stays in <style>; the element itself must not appear.
    assert '<div class="preview-description">' not in response.text


async def test_preview_missing_returns_404(client):
    response = await client.get("/contents/9999")
    assert response.status_code == 404
