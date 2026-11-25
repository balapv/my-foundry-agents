"""Date rebasing so the seeded scenario is always relative to the real current date.

The synthetic dataset is stored against a fixed anchor date (the dataset's "today").
At request time every date in a response is shifted by ``demo_today - anchor`` and
every date received in a request is shifted back. CT218 is therefore always
cancelled *tomorrow*, whenever the demo is run.

The simulated clock is the current wall-clock time in ``DEMO_TIMEZONE`` (default
America/Los_Angeles, the hero's home airport). ``DEMO_TODAY`` (YYYY-MM-DD) pins the date
and ``DEMO_TIME`` (HH:MM) pins the time of day; tests use both.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})(T.*)?$")
DEFAULT_TIMEZONE = "America/Los_Angeles"


def demo_timezone() -> str:
    return os.environ.get("DEMO_TIMEZONE", "").strip() or DEFAULT_TIMEZONE


def demo_now() -> datetime:
    """Current simulated local time (naive, minute precision) in ``DEMO_TIMEZONE``."""
    now = datetime.now(ZoneInfo(demo_timezone())).replace(tzinfo=None, second=0, microsecond=0)
    pinned_day = os.environ.get("DEMO_TODAY", "").strip()
    pinned_time = os.environ.get("DEMO_TIME", "").strip()
    if pinned_day:
        now = datetime.combine(date.fromisoformat(pinned_day), now.time())
    if pinned_time:
        now = datetime.combine(now.date(), time.fromisoformat(pinned_time))
    return now


def demo_today() -> date:
    return demo_now().date()


def offset_days(anchor: date) -> int:
    return (demo_today() - anchor).days


def _shift_string(value: str, days: int) -> str:
    match = _DATE_PREFIX.match(value)
    if not match:
        return value
    try:
        shifted = date.fromisoformat(match.group(1)) + timedelta(days=days)
    except ValueError:
        return value
    return shifted.isoformat() + (match.group(2) or "")


def shift(obj: Any, days: int) -> Any:
    """Return a deep copy of ``obj`` with every ISO date/datetime string shifted by ``days``."""
    if days == 0:
        return obj
    if isinstance(obj, dict):
        return {k: shift(v, days) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shift(v, days) for v in obj]
    if isinstance(obj, str):
        return _shift_string(obj, days)
    return obj


def to_stored_date(requested: str, anchor: date) -> str:
    """Convert a caller-supplied (real-world) YYYY-MM-DD date to the stored dataset date."""
    parsed = date.fromisoformat(requested)
    return (parsed - timedelta(days=offset_days(anchor))).isoformat()
