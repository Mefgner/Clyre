import logging
import re

from scripts.utils.cfg import get_app_runtime_dir
from shared.pyutils.env import Settings

Logger = logging.getLogger(__name__)

_DB_PATH_PATTERN = re.compile(r"^\.(/\w+)+(\.\w{2,})?$")


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
    runtime = s.DB_RUNTIME

    if engine == "sqlite":
        db_path = s.DESKTOP_DB_PATH
        if _DB_PATH_PATTERN.match(db_path):
            resolved = get_app_runtime_dir() / db_path
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.touch(exist_ok=True)
            db_path = resolved.as_posix()

        url = f"{engine}+{runtime}:///{db_path}"
        Logger.info("Built SQLite DATABASE_URL: %s", url)
        return url

    # PostgreSQL, MySQL, etc.
    url = f"{engine}+{runtime}://{s.DESKTOP_DB_PATH}"
    Logger.info("Built DATABASE_URL: %s", url)
    return url


__all__ = ["build_database_url"]
