import datetime


def get_current_timestamp():
    return datetime.datetime.now().timestamp()


def offset_datetime(from_: datetime.datetime, offset: datetime.timedelta):
    return from_ + offset


def get_utc_now():
    return datetime.datetime.now(datetime.UTC)


def utc_from_iso_str(time_str: str):
    return datetime.datetime.fromisoformat(time_str).now(datetime.UTC)


def utc_from_timestamp(timestamp: float):
    return datetime.datetime.fromtimestamp(timestamp, datetime.UTC)


__all__ = [
    "get_current_timestamp",
    "get_utc_now",
    "offset_datetime",
    "utc_from_iso_str",
    "utc_from_timestamp",
]
