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
    REFRESH_TOKEN_SECRET: str
    # SERVICE_SECRET: str = "forbidden"  # Deprecated telegram bot access
    ACCESS_TOKEN_DUR_MINUTES: int = 15
    REFRESH_TOKEN_DUR_DAYS: int = 15

    # Llama configuration
    LLAMA_WIN_HOST: str = "localhost"
    LLAMA_WIN_PORT: int = 6760
    LLAMA_URL: str = "http://localhost:6760"
    LLAMA_MODEL_NAME: str | None = None

    # Embedding inference (second llama-server)
    EMBEDDING_BASE_URL: str = "http://localhost:6761"
    EMBEDDING_MODEL: str = "Qwen3-Embedding-0.6B"

    # Orchestrator configuration
    PRIMARY_MODEL_NAME: str | None = None
    PRIMARY_MODEL_SIZE: str | None = None

    # Vector config
    VECTOR_DIM: int = 512
    DESKTOP_VECTOR_DB_PATH: str = "./data/vectors"
    VECTOR_DB_URL: str | None = None
    NORMALIZE_VECTORS: bool = True

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
