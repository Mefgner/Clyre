from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_app_root_dir() -> Path:
    return Path(__file__).parent.parent.parent.resolve()
