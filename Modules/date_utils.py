"""Shared presentation helpers for Project Ascend dates."""

from datetime import date, datetime


def parse_iso_date(value):
    """Return a ``date`` for an ISO date value, or ``None`` when invalid."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def format_display_date(value, include_weekday=False):
    """Format a date consistently for all user-facing copy.

    Produces "1 January 2026" and "26 August 2026" - the day number is never
    zero-padded, which "%d" would otherwise do on every platform.
    """
    parsed_date = parse_iso_date(value)
    if parsed_date is None:
        return "Date unavailable"
    date_text = f"{parsed_date.day} {parsed_date.strftime('%B %Y')}"
    if include_weekday:
        return f"{parsed_date.strftime('%A')}, {date_text}"
    return date_text


def format_duration(minutes):
    """Format a duration consistently as hours and minutes."""
    total = max(0, int(minutes or 0))
    hours, mins = divmod(total, 60)
    return f"{hours}h {mins}m"
