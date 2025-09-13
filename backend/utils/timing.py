import datetime


def timedelta(from_: datetime.datetime, offset: datetime.timedelta):
    return from_ + offset


def utc_now():
    return datetime.datetime.now(datetime.UTC)


def utc_from_str(time_str: str):
    return datetime.datetime.fromisoformat(time_str).now(datetime.UTC)


__all__ = ["utc_now", "utc_from_str", "timedelta"]
