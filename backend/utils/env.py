from pydantic_settings import BaseSettings
from utils import get_app_root_dir


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
    DB_PATH: str = "./data/clyre.sqlite3"

    # Hashing
    HASHING_SECRET: str = "your_secret_key_here"
    ACCESS_TOKEN_SECRET: str = "your_secret_key_here"
    REFRESH_TOKEN_SECRET: str = "your_secret_key_here"
    SERVICE_SECRET: str = "forbidden"
    ACCESS_TOKEN_DUR_MINUTES: int = 15
    REFRESH_TOKEN_DUR_DAYS: int = 15

    # Llama configuration
    LLAMA_WIN_HOST: str = "localhost"
    LLAMA_WIN_PORT: int = 6760
    LLAMA_URL: str = "http://localhost:6760"

    # Vector config
    VECTOR_DB: str = "faiss"
    VECTOR_DIM: int = 512
    VECTOR_PATH: str = "./data/vectors"
    NORMALIZE_VECTORS: bool = False
    DISTANCE: str = "cosine"

    class Config:
        env_file = env_file()
