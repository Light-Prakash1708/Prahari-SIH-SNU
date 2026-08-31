"""
PRAHARI · one clock
════════════════════════════════════════════════════════════════════════════
Every date in this system comes from here. The seed, the risk models, the
follow-up scheduler and the officer queue must agree on what "today" is, or a
follow-up is overdue the moment it is created.

PRAHARI_TODAY pins the date for a reproducible demo. config.py refuses it in
production, so a deployment cannot be run against a frozen clock by accident.
"""
from __future__ import annotations

import datetime as dt

from .config import get_settings


def today() -> dt.date:
    s = get_settings()
    if s.prahari_today and not s.is_production:
        try:
            return dt.date.fromisoformat(s.prahari_today)
        except ValueError:
            pass
    return dt.datetime.now(dt.UTC).astimezone(IST).date()


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now() -> dt.datetime:
    """The wall clock, shifted onto the pinned day when PRAHARI_TODAY is set.

    This is not a nicety. The prototype stamped rows with the operating system's
    clock while every date calculation came from a pinned one, so the moment the
    real date rolled past the pinned date, an observation recorded "today" was
    dated tomorrow — and a follow-up could no longer find the scan it was
    supposed to compare against. One clock, or none.

    config.py refuses PRAHARI_TODAY in production, so this branch is
    unreachable on a deployed instance."""
    real = dt.datetime.now(dt.UTC)
    s = get_settings()
    if s.prahari_today and not s.is_production:
        try:
            pinned = dt.date.fromisoformat(s.prahari_today)
        except ValueError:
            return real
        return real.replace(year=pinned.year, month=pinned.month, day=pinned.day)
    return real


def real_now() -> dt.datetime:
    """The genuine wall clock, never shifted.

    Anything a protocol validates against its own clock uses this: JWT iat/exp,
    session expiry, password-reset windows. Domain time may be pinned for a
    reproducible demo; token time may not, because PyJWT checks exp against the
    real clock and a shifted token would be born expired."""
    return dt.datetime.now(dt.UTC)


def real_iso() -> str:
    return real_now().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_iso() -> str:
    """The canonical timestamp format for every {{TS}} column: UTC, milliseconds,
    trailing Z. Fixed width, so lexicographic order is chronological order — and
    milliseconds rather than seconds because three trap counts entered in one
    second must still come back in the order they were made."""
    return now().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso(ts: dt.datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return (ts.astimezone(dt.UTC)
            .isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        out = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=dt.UTC)


def days_ago(value: str | None) -> int | None:
    ts = parse_ts(value)
    if ts is None:
        return None
    return (now() - ts).days


def date_str(d: dt.date) -> str:
    return d.isoformat()


def plus_days(d: dt.date, n: int) -> dt.date:
    return d + dt.timedelta(days=n)
