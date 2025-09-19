from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_app_root_dir() -> Path:
    res = Path(__file__).parent.parent.resolve()
    return res


from . import env

Settings = env.Settings
env = Settings()
