"""Per-date available-time storage for Planner Capacity Intelligence.

Available time is the ONLY new persistent value this feature introduces,
and it is written exclusively when the user explicitly enters it.

Storage
-------
The value lives in the existing ``settings`` key/value table under one
key, as a JSON object mapping an ISO date to whole minutes::

    planner_available_minutes -> {"2026-08-16": 180, "2026-08-17": 240}

No new table, no new column, no schema-version change and no migration:
the generic settings table already exists for exactly this kind of small
permanent preference, and the existing public
``Database.get_setting`` / ``Database.set_setting`` API is the only
persistence path used here.

Product safeguards owned by this module
---------------------------------------
* Available time is NEVER derived, guessed or defaulted. Absent means
  absent: ``get`` returns ``None`` and the planner shows no fit verdict.
  In particular the daily goal is never read here - a goal is an
  achievement target, not a statement of available time.
* ``0`` is a legitimate stored value ("I have no time that day") and is
  deliberately distinct from ``None`` ("I have not said").
* Corrupt, missing or foreign-shaped JSON is treated as "no data" rather
  than raising or resetting anything. A planner screen must never fail
  to open because a preference could not be parsed.
* Only this one key is ever written. ``daily_goal``, ``total_xp`` and
  every other setting are untouched.
* Entries outside the retention window are pruned on write so the stored
  value stays small; the value being written is always kept.

The module is Qt-free so it is fully testable without a GUI.
"""

import json

from Modules.date_utils import parse_iso_date


# The single settings key this feature owns.
SETTING_KEY = "planner_available_minutes"

# Retention window applied on write, relative to today. Capacity is a
# planning aid for the near future, so old entries are not kept forever.
RETENTION_DAYS_PAST = 7
RETENTION_DAYS_FUTURE = 30

# Accepted bounds for a stored value. 0 means "no time available that
# day" and is a real answer; 1440 is one full day, matching the existing
# daily-goal maximum used elsewhere in the app.
MIN_AVAILABLE_MINUTES = 0
MAX_AVAILABLE_MINUTES = 1440


def clamp_minutes(minutes):
    """Return ``minutes`` as a whole number inside the accepted bounds.

    Mirrors the defensive clamping ``Database.set_daily_goal`` already
    applies to user-entered durations.
    """
    value = int(minutes)
    value = max(MIN_AVAILABLE_MINUTES, value)
    return min(value, MAX_AVAILABLE_MINUTES)


class AvailableTimeStore:
    """Read and write the user's stated available time for a date.

    The store only ever touches ``SETTING_KEY``. Every read is
    defensive: any value that is not a usable date -> minutes mapping is
    reported as "no data".
    """

    def __init__(self, database):
        self.database = database

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, plan_date):
        """Return the stored minutes for a date, or ``None``.

        ``None`` means the user has not stated their available time.
        It is never replaced with a default, a goal or a guess.
        """
        entries = self.load_entries()
        return entries.get(self.normalize_date(plan_date))

    def set(self, plan_date, minutes):
        """Store the user's explicitly entered available time for a date.

        Returns the value actually persisted, so callers can mirror the
        clamped result back into their input field.
        """
        key = self.normalize_date(plan_date)
        if key is None:
            return None

        value = clamp_minutes(minutes)
        entries = self.load_entries()
        entries[key] = value
        self.save_entries(entries, keep=key)
        return value

    def clear(self, plan_date):
        """Remove a date's available time, returning the planner to the
        "no available-time information" state. Clearing a date that was
        never set is a no-op."""
        key = self.normalize_date(plan_date)
        entries = self.load_entries()

        if key not in entries:
            return

        del entries[key]
        self.save_entries(entries)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def load_entries(self):
        """Return the stored date -> minutes mapping, or ``{}``.

        Every failure mode - missing key, unreadable database, invalid
        JSON, wrong JSON shape, unparseable dates, non-numeric or
        out-of-range values - collapses to "no data" for the affected
        entries. Nothing is repaired in place and nothing is deleted as
        a side effect of reading.
        """
        try:
            raw = self.database.get_setting(SETTING_KEY)
        except Exception:
            return {}

        if not raw:
            return {}

        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return {}

        if not isinstance(decoded, dict):
            return {}

        entries = {}
        for key, value in decoded.items():
            normalized = self.normalize_date(key)
            if normalized is None:
                continue
            minutes = self.normalize_minutes(value)
            if minutes is None:
                continue
            entries[normalized] = minutes

        return entries

    def save_entries(self, entries, keep=None):
        """Persist the mapping, pruning entries outside the retention
        window. ``keep`` is never pruned, so writing a value always
        stores that value."""
        pruned = self.prune(entries, keep=keep)
        self.database.set_setting(
            SETTING_KEY,
            json.dumps(pruned, sort_keys=True),
        )

    def prune(self, entries, keep=None, today=None):
        """Drop entries that are too far in the past or the future."""
        from datetime import date, timedelta

        reference = today or date.today()
        earliest = reference - timedelta(days=RETENTION_DAYS_PAST)
        latest = reference + timedelta(days=RETENTION_DAYS_FUTURE)

        pruned = {}
        for key, value in entries.items():
            if key == keep:
                pruned[key] = value
                continue
            parsed = parse_iso_date(key)
            if parsed is None:
                continue
            if earliest <= parsed <= latest:
                pruned[key] = value

        return pruned

    # ------------------------------------------------------------------
    # Value normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_date(plan_date):
        """Return a canonical ISO date string, or ``None`` when the
        value is not a usable date."""
        parsed = parse_iso_date(plan_date)
        if parsed is None:
            return None
        return parsed.isoformat()

    @staticmethod
    def normalize_minutes(value):
        """Return a usable whole-minute value, or ``None``.

        Booleans, text, floats with a fractional part and out-of-range
        numbers are rejected rather than coerced: a stored capacity
        value must be exactly what the user entered.
        """
        if isinstance(value, bool):
            return None
        if not isinstance(value, int):
            return None
        if value < MIN_AVAILABLE_MINUTES or value > MAX_AVAILABLE_MINUTES:
            return None
        return value
