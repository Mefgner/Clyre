import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field
from pydantic_settings import BaseSettings

from shared.pyutils.base import get_app_root_dir


def env_file():
    prod_env = get_app_root_dir() / ".env"
    if prod_env.exists():
        return prod_env


NonEmptySecret = Annotated[str, Field(min_length=1)]


class Settings(BaseSettings):
    # General configuration
    CLYRE_VERSION: str = "0.0.1"
    DEBUG: bool = False
    TEST_MODE: bool = False

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

    # Hashing / auth secrets must be present and non-empty. Compose already
    # enforces this; desktop Settings now has the same invariant.
    HASHING_SECRET: NonEmptySecret
    ACCESS_TOKEN_SECRET: NonEmptySecret
    # SERVICE_SECRET: str = "forbidden"  # Deprecated telegram bot access
    ACCESS_TOKEN_DUR_MINUTES: int = 15
    REFRESH_TOKEN_DUR_DAYS: int = 15

    # Model endpoints. env holds only overrides: the base URL where the model is
    # served and the model name/alias sent in requests. All cognitive roles share
    # the chat endpoint; role-specific behavior belongs in call profiles.
    CHAT_BASE_URL: str | None = None
    CHAT_MODEL: str | None = None
    EMBEDDING_BASE_URL: str | None = None  # RAG; required
    EMBEDDING_MODEL: str | None = None

    # Local llama-server bind addresses (desktop launcher)
    CHAT_BIND_HOST: str = "localhost"
    CHAT_BIND_PORT: int = 6760
    EMBEDDING_BIND_HOST: str = "localhost"
    EMBEDDING_BIND_PORT: int = 6761

    # Vector config
    VECTOR_DIM: int = 1024
    DESKTOP_VECTOR_DB_PATH: str = "./data/vectors"
    VECTOR_DB_URL: str | None = None
    NORMALIZE_VECTORS: bool = True
    CHUNK_SIZE: int = 1500
    CHUNK_OVERLAP: int = 200

    # M3 chat attachments: all values must stay positive.
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    MAX_THREAD_ATTACHMENTS: int = 16
    CHAT_MAX_OUTPUT_TOKENS: int = 1024

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
