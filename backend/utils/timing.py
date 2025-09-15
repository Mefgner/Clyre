import datetime


def get_unix_timestamp():
    return datetime.datetime.now().timestamp()


def get_timedelta(from_: datetime.datetime, offset: datetime.timedelta):
    return from_ + offset


def get_utc_now():
    return datetime.datetime.now(datetime.UTC)


def utc_from_str(time_str: str):
    return datetime.datetime.fromisoformat(time_str).now(datetime.UTC)


__all__ = ["get_utc_now", "utc_from_str", "get_timedelta", "get_unix_timestamp"]
