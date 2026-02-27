"""Simple config-driven availability: fixed windows per day, no calendar yet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# Two windows per weekday: 9–12 and 13–16 (local). Stored as label for display.
DEFAULT_WINDOWS = ["9:00 AM–12:00 PM", "1:00 PM–4:00 PM"]
DAYS_AHEAD = 7


@dataclass
class Slot:
    """A bookable time slot (date + window label)."""
    date_str: str  # YYYY-MM-DD
    window: str
    slot_id: str  # e.g. "2026-03-01_1" for second window that day


def list_slots() -> list[Slot]:
    """Return the next DAYS_AHEAD days, each with DEFAULT_WINDOWS. No availability check yet."""
    today = date.today()
    slots: list[Slot] = []
    for i in range(DAYS_AHEAD):
        d = today + timedelta(days=i)
        date_str = d.isoformat()
        for j, window in enumerate(DEFAULT_WINDOWS):
            slots.append(Slot(date_str=date_str, window=window, slot_id=f"{date_str}_{j}"))
    return slots


def slot_from_id(slot_id: str) -> Slot | None:
    """Parse slot_id (date_str_index) into a Slot if valid."""
    parts = slot_id.rsplit("_", 1)
    if len(parts) != 2:
        return None
    date_str, idx_str = parts
    try:
        d = date.fromisoformat(date_str)
        idx = int(idx_str)
        if 0 <= idx < len(DEFAULT_WINDOWS):
            return Slot(date_str=date_str, window=DEFAULT_WINDOWS[idx], slot_id=slot_id)
    except (ValueError, TypeError):
        pass
    return None


def format_slot_for_sms(slot: Slot) -> str:
    """Human-readable slot for SMS (e.g. 'Thu 03/01, 1:00 PM–4:00 PM')."""
    try:
        d = date.fromisoformat(slot.date_str)
        short_date = d.strftime("%a %m/%d")
    except (ValueError, TypeError):
        short_date = slot.date_str
    return f"{short_date}, {slot.window}"
