import datetime
from functools import lru_cache

from utils import env


@lru_cache(maxsize=1)
def get_access_token_dur_minutes() -> datetime.timedelta:
    return datetime.timedelta(minutes=int(env.ACCESS_TOKEN_DUR_MINUTES))


@lru_cache(maxsize=1)
def get_refresh_token_dur_days() -> datetime.timedelta:
    return datetime.timedelta(days=int(env.REFRESH_TOKEN_DUR_DAYS))


__all__ = [
    "get_access_token_dur_minutes",
    "get_refresh_token_dur_days",
]
