"""Shared pytest fixtures.

The env var dance at the top is intentional: ``app.config.settings`` and
``app.db.engine`` are constructed at module import time. We need each test
session to use an isolated tmp storage directory, so we set ``STORAGE_DIR``
*before* any ``app.*`` module is imported.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import AsyncIterator

import pytest

# Must happen before importing app.* — pydantic-settings reads env on class load.
_TEST_STORAGE = tempfile.mkdtemp(prefix="digsig-test-")
os.environ["STORAGE_DIR"] = _TEST_STORAGE
# Default fake key so the selection service doesn't short-circuit; tests that
# care about the network path monkeypatch ``_post_chat`` anyway.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.api.main import app as fastapi_app  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.storage import ensure_dirs  # noqa: E402
import app.models  # noqa: E402, F401  -- registers tables on SQLModel.metadata


async def _reset_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _session_storage():
    ensure_dirs()
    yield
    shutil.rmtree(_TEST_STORAGE, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_db_and_storage():
    """Fresh tables + empty pools dir for every test.

    Sync so it works for both async (services, routes) and sync (CLI) tests
    without colliding with their event loops.
    """
    asyncio.run(_reset_tables())
    if settings.pools_dir.exists():
        shutil.rmtree(settings.pools_dir)
    settings.pools_dir.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
async def session() -> AsyncIterator:
    async with SessionLocal() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
