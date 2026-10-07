"""Daily schedule window helpers."""

from __future__ import annotations

from datetime import datetime, time


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def in_schedule_window(now: datetime, start: str, stop: str) -> bool:
    """Return True if now is inside [start, stop), supporting overnight windows."""
    start_t = parse_hhmm(start)
    stop_t = parse_hhmm(stop)
    current = now.time().replace(second=0, microsecond=0)

    if start_t == stop_t:
        # Degenerate: treat as always off
        return False

    if start_t < stop_t:
        return start_t <= current < stop_t

    # Overnight: e.g. 22:00 -> 02:00
    return current >= start_t or current < stop_t
