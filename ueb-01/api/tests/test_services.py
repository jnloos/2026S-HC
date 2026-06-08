"""Tests for the pool/content service layer (CRUD + on-disk side-effects)."""
import pytest

from app.services import contents as content_service
from app.services import pools as pool_service
from app.storage import content_path, pool_dir


async def test_create_and_list_pool(session):
    p = await pool_service.create_pool(session, name="rainy", description="cold-weather screens")
    assert p.id is not None
    assert p.name == "rainy"

    pools = await pool_service.list_pools(session)
    assert [pp.name for pp in pools] == ["rainy"]


async def test_add_content_writes_file(session):
    pool = await pool_service.create_pool(session, name="kids")
    c = await content_service.add_content(
        session,
        pool_id=pool.id,
        name="cartoon",
        html="<h1>Hi kids</h1>",
        description="for children under 10",
    )
    assert c.id is not None
    assert c.description == "for children under 10"
    path = content_path(pool.id, c.id)
    assert path.exists()
    assert path.read_text() == "<h1>Hi kids</h1>"


async def test_add_content_description_defaults_to_empty(session):
    pool = await pool_service.create_pool(session, name="adults")
    c = await content_service.add_content(
        session, pool_id=pool.id, name="x", html="<p>x</p>"
    )
    assert c.description == ""


async def test_read_html_roundtrips(session):
    pool = await pool_service.create_pool(session, name="adults")
    c = await content_service.add_content(session, pool_id=pool.id, name="x", html="<p>ok</p>")
    assert await content_service.read_html(c) == "<p>ok</p>"


async def test_list_for_pool_filters_by_pool(session):
    a = await pool_service.create_pool(session, name="a")
    b = await pool_service.create_pool(session, name="b")
    await content_service.add_content(session, pool_id=a.id, name="a1", html="<i>1</i>")
    await content_service.add_content(session, pool_id=a.id, name="a2", html="<i>2</i>")
    await content_service.add_content(session, pool_id=b.id, name="b1", html="<i>3</i>")

    in_a = await content_service.list_for_pool(session, a.id)
    in_b = await content_service.list_for_pool(session, b.id)
    assert {c.name for c in in_a} == {"a1", "a2"}
    assert {c.name for c in in_b} == {"b1"}


async def test_delete_content_removes_file(session):
    pool = await pool_service.create_pool(session, name="p")
    c = await content_service.add_content(session, pool_id=pool.id, name="x", html="<p>x</p>")
    path = content_path(pool.id, c.id)
    assert path.exists()

    assert await content_service.delete_content(session, c.id) is True
    assert not path.exists()
    assert await content_service.get_content(session, c.id) is None


async def test_delete_pool_cascades_contents_and_dir(session):
    pool = await pool_service.create_pool(session, name="p")
    c1 = await content_service.add_content(session, pool_id=pool.id, name="x", html="x")
    c2 = await content_service.add_content(session, pool_id=pool.id, name="y", html="y")
    pdir = pool_dir(pool.id)
    assert pdir.exists()

    assert await pool_service.delete_pool(session, pool.id) is True

    assert await pool_service.get_pool(session, pool.id) is None
    assert await content_service.get_content(session, c1.id) is None
    assert await content_service.get_content(session, c2.id) is None
    assert not pdir.exists()


async def test_delete_missing_returns_false(session):
    assert await pool_service.delete_pool(session, 999) is False
    assert await content_service.delete_content(session, 999) is False
