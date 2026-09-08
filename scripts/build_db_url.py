import logging
from pathlib import Path

from scripts.utils.cfg import get_app_runtime_dir
from shared.pyutils.env import Settings

Logger = logging.getLogger(__name__)


def _resolve_sqlite_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    path = Path(normalized)
    if not path.is_absolute():
        path = get_app_runtime_dir() / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path


def build_database_url(settings: Settings | None = None) -> str:
    """
    Build a DATABASE_URL from settings.

    Priority:
        1. DATABASE_URL env var (already set) → return as-is
        2. Construct from DB_ENGINE + DB_RUNTIME + DB_PATH
    """
    s = settings or Settings()

    if s.DATABASE_URL:
        Logger.info("Using pre-configured DATABASE_URL")
        return s.DATABASE_URL

    engine = s.DB_ENGINE

    if engine == "sqlite":
        runtime = s.DB_RUNTIME or "aiosqlite"
        db_path = _resolve_sqlite_path(s.DESKTOP_DB_PATH).as_posix()
        url = f"sqlite+{runtime}:///{db_path}"
        Logger.info("Built SQLite DATABASE_URL: %s", url)
        return url

    runtime = s.DB_RUNTIME
    if engine == "postgresql" and runtime == "aiosqlite":
        runtime = "asyncpg"

    driver = f"+{runtime}" if runtime else ""
    url = f"{engine}{driver}://{s.DESKTOP_DB_PATH}"
    Logger.info("Built DATABASE_URL: %s", url)
    return url


__all__ = ["build_database_url"]
