import logging

from pydantic_settings import BaseSettings

from shared.pyutils.base import get_app_root_dir


def env_file():
    prod_env = get_app_root_dir() / ".env"
    if prod_env.exists():
        return prod_env
    return get_app_root_dir() / "configs" / "base.env"


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

    # Hashing
    HASHING_SECRET: str = "your_secret_key_here"
    ACCESS_TOKEN_SECRET: str = "your_secret_key_here"
    REFRESH_TOKEN_SECRET: str = "your_secret_key_here"
    # SERVICE_SECRET: str = "forbidden"  # Deprecated telegram bot access
    ACCESS_TOKEN_DUR_MINUTES: int = 15
    REFRESH_TOKEN_DUR_DAYS: int = 15

    # Llama configuration
    LLAMA_WIN_HOST: str = "localhost"
    LLAMA_WIN_PORT: int = 6760
    LLAMA_URL: str = "http://localhost:6760"
    LLAMA_MODEL_NAME: str = ""

    # Vector config
    VECTOR_DIM: int = 512
    DESKTOP_VECTOR_PATH: str = "./data/vectors"
    VECTOR_URL: str | None = None
    NORMALIZE_VECTORS: bool = True
    

    class Config:
        env_file = env_file()
        extra = "ignore"


def get_logging_level() -> int:
    return logging.DEBUG if Settings().DEBUG else logging.INFO


__all__ = ["Settings", "env_file", "get_logging_level"]
