"""Datetimes are stored in UTC. Calendar days (goals, streaks, weekly ranges) use the
machine's local timezone, which in Docker comes from the TZ variable."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, func


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    # SQLite gives back naive datetimes; by convention they are UTC.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_date(dt: datetime) -> date:
    return as_utc(dt).astimezone().date()


def local_day(column):
    """SQL expression for the local calendar day of a UTC datetime column."""
    return func.date(column, "localtime", type_=Date)
