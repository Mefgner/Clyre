import datetime


def get_current_timestamp():
    return get_utc_now().timestamp()


def offset_datetime(from_: datetime.datetime, offset: datetime.timedelta):
    return from_ + offset


def get_utc_now():
    return datetime.datetime.now(datetime.UTC)


def ensure_utc(dt: datetime.datetime):
    return dt.replace(tzinfo=datetime.UTC) if dt.tzinfo is None else dt


def utc_from_timestamp(timestamp: float):
    return datetime.datetime.fromtimestamp(timestamp, datetime.UTC)


__all__ = [
    "ensure_utc",
    "get_current_timestamp",
    "get_utc_now",
    "offset_datetime",
    "utc_from_timestamp",
]
