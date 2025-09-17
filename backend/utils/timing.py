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


__all__ = ["get_utc_now", "utc_from_iso_str", "offset_datetime", "get_current_timestamp", "utc_from_timestamp"]
