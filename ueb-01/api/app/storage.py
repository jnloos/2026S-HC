"""Filesystem layout for runtime data (DB + content HTML files).

Layout:

    storage/
    ├── db/digsig.db
    └── pools/
        └── <pool_id>/
            └── <content_id>.html
"""
from pathlib import Path

from app.config import settings


def ensure_dirs() -> None:
    """Create the top-level storage directories.

    Called on app startup and before DB init; SQLite will not create the
    parent directory of its database file on its own. Per-pool directories
    are created lazily by ``pool_dir()``.
    """
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.pools_dir.mkdir(parents=True, exist_ok=True)


def pool_dir(pool_id: int, *, create: bool = False) -> Path:
    """Path to a single pool's directory."""
    path = settings.pools_dir / str(pool_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def content_path(pool_id: int, content_id: int) -> Path:
    """Filesystem path for a content's HTML snippet."""
    return pool_dir(pool_id) / f"{content_id}.html"
