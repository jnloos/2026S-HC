"""Business logic for contents — called by both API routes and CLI commands.

A content belongs to exactly one pool. The HTML snippet lives on disk under
``storage/pools/<pool_id>/<content_id>.html``; only metadata is in the DB.

Two-phase create: insert DB row to mint the content id, then write the file
using that id as the filename. If the file write fails the row is rolled back.
"""
from collections.abc import Sequence

import aiofiles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Content
from app.storage import content_path, pool_dir


async def add_content(
    session: AsyncSession,
    *,
    pool_id: int,
    name: str,
    html: str,
    description: str = "",
) -> Content:
    """Persist a content row + write its HTML file. Atomic-ish: on file
    failure the DB row is rolled back so we don't end up with phantom rows."""
    content = Content(pool_id=pool_id, name=name, description=description)
    session.add(content)
    await session.commit()
    await session.refresh(content)

    try:
        pool_dir(pool_id, create=True)
        async with aiofiles.open(content_path(pool_id, content.id), "w", encoding="utf-8") as f:
            await f.write(html)
    except Exception:
        # Intentionally broad: the row was already committed to mint the id, so
        # ANY failure writing the file (OSError, encoding, disk full, ...) must
        # roll it back — otherwise we leave a phantom row with no HTML file. The
        # original error is re-raised unchanged for the caller to handle.
        await session.delete(content)
        await session.commit()
        raise

    return content


async def list_for_pool(session: AsyncSession, pool_id: int) -> Sequence[Content]:
    result = await session.exec(
        select(Content).where(Content.pool_id == pool_id).order_by(Content.id)
    )
    return result.all()


async def get_content(session: AsyncSession, content_id: int) -> Content | None:
    return await session.get(Content, content_id)


async def read_html(content: Content) -> str:
    """Read the HTML snippet from disk."""
    async with aiofiles.open(content_path(content.pool_id, content.id), encoding="utf-8") as f:
        return await f.read()


async def delete_content(session: AsyncSession, content_id: int) -> bool:
    """Delete a content row and remove its HTML file. Returns False if not found."""
    content = await session.get(Content, content_id)
    if content is None:
        return False
    path = content_path(content.pool_id, content.id)
    await session.delete(content)
    await session.commit()
    path.unlink(missing_ok=True)
    return True
