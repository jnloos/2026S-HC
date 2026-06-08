"""Application settings, loaded from environment / .env file.

Paths are derived from a fixed storage directory so the DB and content files
live in the same place regardless of the current working directory.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# api/  (this file is api/app/config.py)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DigSig API"

    # Root for all mutable runtime data (DB + content files). Overridable via env.
    storage_dir: Path = BASE_DIR / "storage"

    # Optional explicit DB URL; if empty it is derived from storage_dir.
    database_url: str = ""

    # Anthropic API — required for /choose-by-group and /choose-by-img endpoints.
    # Haiku 4.5 is the cheapest multimodal Claude model and supports structured outputs.
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"
    claude_max_tokens: int = 1024
    claude_timeout_seconds: float = 30.0

    # Debug UI — opt-in observability surface (live SSE stream + recent buffer).
    # Off by default so production-ish deployments don't expose internals.
    debug_ui_enabled: bool = False
    # Empty = no auth (lab/LAN). Non-empty = require ?token=... or Bearer header.
    debug_token: str = ""

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "db" / "digsig.db"

    @property
    def pools_dir(self) -> Path:
        return self.storage_dir / "pools"

    @property
    def resolved_database_url(self) -> str:
        # SQLite + absolute path needs four slashes: sqlite+aiosqlite:////abs/path
        return self.database_url or f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()
