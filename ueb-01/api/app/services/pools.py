"""Business logic for pools — called by both API routes and CLI commands.

A pool is a named bucket of HTML snippets. Deleting a pool cascades to its
contents (DB) and removes the pool directory on disk.
"""
import shutil
from collections.abc import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Pool
from app.storage import pool_dir


async def create_pool(session: AsyncSession, *, name: str, description: str = "") -> Pool:
    pool = Pool(name=name, description=description)
    session.add(pool)
    await session.commit()
    await session.refresh(pool)
    return pool


async def list_pools(session: AsyncSession) -> Sequence[Pool]:
    result = await session.exec(select(Pool).order_by(Pool.id))
    return result.all()


async def get_pool(session: AsyncSession, pool_id: int) -> Pool | None:
    return await session.get(Pool, pool_id)


async def find_pool_by_name(session: AsyncSession, name: str) -> Pool | None:
    result = await session.exec(select(Pool).where(Pool.name == name))
    return result.first()


async def delete_pool(session: AsyncSession, pool_id: int) -> bool:
    """Delete a pool and its on-disk directory. Returns False if not found."""
    pool = await session.get(Pool, pool_id)
    if pool is None:
        return False
    await session.delete(pool)
    await session.commit()
    shutil.rmtree(pool_dir(pool_id), ignore_errors=True)
    return True
