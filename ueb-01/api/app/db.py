"""Database engine, session factory and SQLite tuning.

Uses SQLModel for the ORM layer on top of SQLAlchemy's async engine. Shared by
both the web layer (FastAPI routes via ``get_session``) and the console layer
(CLI commands via ``SessionLocal``).
"""
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

engine = create_async_engine(settings.resolved_database_url)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """Apply SQLite tuning on every new connection.

    WAL lets readers and writers work concurrently; busy_timeout avoids
    spurious "database is locked" errors; synchronous=NORMAL is safe with WAL
    and much faster than the FULL default; foreign_keys enforces constraints.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session per request."""
    async with SessionLocal() as session:
        yield session
