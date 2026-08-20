import logging
from typing import TYPE_CHECKING, Any

from pydantic_settings import BaseSettings

from shared.pyutils.base import get_app_root_dir


def env_file():
    prod_env = get_app_root_dir() / ".env"
    if prod_env.exists():
        return prod_env


class Settings(BaseSettings):
    # General configuration
    CLYRE_VERSION: str = "0.0.1"
    DEBUG: bool = False

    # Server configuration
    HOST: str = "localhost"
    PORT: int = 6750

    # Backend configuration
    DB_ENGINE: str = "sqlite"
    DB_RUNTIME: str = "aiosqlite"
    DESKTOP_DB_PATH: str = "./data/clyre.sqlite3"
    DATABASE_URL: str | None = None

    # File storage (raw uploaded bytes; relative paths anchor to the app root)
    FILES_DIR: str = "./data/files"

    # Hashing
    HASHING_SECRET: str
    ACCESS_TOKEN_SECRET: str
    # SERVICE_SECRET: str = "forbidden"  # Deprecated telegram bot access
    ACCESS_TOKEN_DUR_MINUTES: int = 15
    REFRESH_TOKEN_DUR_DAYS: int = 15

    # Inference tiers. env holds only overrides: the base URL (where the tier is
    # served) and the model name/alias to send in requests. When unset, values are
    # resolved from the model catalog (configs/models.yaml) and the local bind
    # addresses below. BIG_* may be left empty -> it falls back to SMALL_*.
    SMALL_BASE_URL: str | None = None  # chat + worker steps
    SMALL_MODEL: str | None = None
    BIG_BASE_URL: str | None = None  # planner + synthesizer (optional)
    BIG_MODEL: str | None = None
    EMBEDDING_BASE_URL: str | None = None  # RAG; required
    EMBEDDING_MODEL: str | None = None

    # Local llama-server bind addresses (desktop launcher)
    SMALL_BIND_HOST: str = "localhost"
    SMALL_BIND_PORT: int = 6760
    BIG_BIND_HOST: str = "localhost"
    BIG_BIND_PORT: int = 6762
    EMBEDDING_BIND_HOST: str = "localhost"
    EMBEDDING_BIND_PORT: int = 6761

    # Vector config
    VECTOR_DIM: int = 1024
    DESKTOP_VECTOR_DB_PATH: str = "./data/vectors"
    VECTOR_DB_URL: str | None = None
    NORMALIZE_VECTORS: bool = True
    CHUNK_SIZE: int = 1500
    CHUNK_OVERLAP: int = 200

    class Config:
        env_file = env_file()
        extra = "ignore"

    if TYPE_CHECKING:
        # Fields are populated from the environment / .env at runtime; this stub
        # tells the type checker no constructor arguments are required.
        def __init__(self, **kwargs: Any) -> None: ...


def get_logging_level() -> int:
    return logging.DEBUG if Settings().DEBUG else logging.INFO


__all__ = ["Settings", "get_logging_level"]
