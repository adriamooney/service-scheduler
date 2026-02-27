"""Quiet hours and basic rate limiting for outbound SMS."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

QUIET_START_HOUR = 21  # 9 PM
QUIET_END_HOUR = 8     # 8 AM
DEFAULT_TZ = "America/Los_Angeles"

ALLOW_FULL_REPLY = "ALLOW_FULL_REPLY"
THROTTLED_REPLY = "THROTTLED_REPLY"
QUIET_HOURS_MESSAGE = "We got your message. We'll respond during business hours (8 AM–9 PM)."


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("TIMEZONE", DEFAULT_TZ))
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _in_quiet_hours(now: datetime | None = None) -> bool:
    """True if current local time is between QUIET_END_HOUR and QUIET_START_HOUR (e.g. 9 PM–8 AM)."""
    dt = (now or datetime.now()).astimezone(_tz())
    hour = dt.hour
    start = int(os.environ.get("QUIET_HOURS_START", QUIET_START_HOUR))
    end = int(os.environ.get("QUIET_HOURS_END", QUIET_END_HOUR))
    if end < start:  # e.g. 21–8: quiet from 21:00 to 23:59 and 0:00 to 7:59
        return hour >= start or hour < end
    return start <= hour < end


def check_reply_allowed() -> tuple[str, str | None]:
    """
    Returns (decision, throttle_message).
    - ALLOW_FULL_REPLY, None: do full LLM reply and send it.
    - THROTTLED_REPLY, msg: send only msg (e.g. quiet hours), do not run LLM for this turn.
    """
    if _in_quiet_hours():
        return THROTTLED_REPLY, QUIET_HOURS_MESSAGE
    return ALLOW_FULL_REPLY, None
