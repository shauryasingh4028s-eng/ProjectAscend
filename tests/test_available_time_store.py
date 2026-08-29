"""Available-time persistence for Planner Capacity Intelligence.

The user's stated available time is the only new persistent value this
feature introduces. It lives in the existing settings key/value table
under one key, so these tests also guard what must NOT change: no
schema version bump, no new table, and no effect on any other setting.
"""

import json
import sqlite3

import pytest

from Database.database import SCHEMA_VERSION, Database
from Modules.available_time_store import (
    MAX_AVAILABLE_MINUTES,
    SETTING_KEY,
    AvailableTimeStore,
)


TOMORROW = None  # replaced per-test by a real date inside the window


@pytest.fixture
def store(database):
    return AvailableTimeStore(database)


@pytest.fixture
def plan_date():
    from datetime import date, timedelta

    return (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def other_date():
    from datetime import date, timedelta

    return (date.today() + timedelta(days=2)).isoformat()


class TestSetGetClear:
    def test_unset_date_returns_none(self, store, plan_date):
        assert store.get(plan_date) is None

    def test_set_then_get(self, store, plan_date):
        store.set(plan_date, 180)

        assert store.get(plan_date) == 180

    def test_set_returns_the_persisted_value(self, store, plan_date):
        assert store.set(plan_date, 180) == 180

    def test_zero_is_a_real_stored_value(self, store, plan_date):
        store.set(plan_date, 0)

        assert store.get(plan_date) == 0
        assert store.get(plan_date) is not None

    def test_overwrite_replaces_the_value(self, store, plan_date):
        store.set(plan_date, 180)
        store.set(plan_date, 240)

        assert store.get(plan_date) == 240

    def test_clear_removes_the_value(self, store, plan_date):
        store.set(plan_date, 180)
        store.clear(plan_date)

        assert store.get(plan_date) is None

    def test_clear_unset_date_is_a_no_op(self, store, plan_date):
        store.clear(plan_date)

        assert store.get(plan_date) is None

    def test_clearing_one_date_keeps_the_other(
        self, store, plan_date, other_date
    ):
        store.set(plan_date, 180)
        store.set(other_date, 240)
        store.clear(plan_date)

        assert store.get(plan_date) is None
        assert store.get(other_date) == 240

    def test_values_are_clamped_to_the_accepted_range(
        self, store, plan_date
    ):
        assert store.set(plan_date, 99999) == MAX_AVAILABLE_MINUTES
        assert store.set(plan_date, -30) == 0


class TestMultipleDates:
    def test_dates_are_independent(self, store, plan_date, other_date):
        store.set(plan_date, 180)
        store.set(other_date, 240)

        assert store.get(plan_date) == 180
        assert store.get(other_date) == 240

    def test_stored_shape_is_a_date_to_minutes_object(
        self, store, database, plan_date, other_date
    ):
        store.set(plan_date, 180)
        store.set(other_date, 240)

        decoded = json.loads(database.get_setting(SETTING_KEY))

        assert decoded == {plan_date: 180, other_date: 240}


class TestRestartPersistence:
    def test_value_survives_a_database_restart(self, tmp_path, plan_date):
        path = tmp_path / "restart.db"

        first = Database(path)
        AvailableTimeStore(first).set(plan_date, 195)
        first.close()

        second = Database(path)
        try:
            assert AvailableTimeStore(second).get(plan_date) == 195
        finally:
            second.close()

    def test_cleared_value_stays_cleared(self, tmp_path, plan_date):
        path = tmp_path / "restart_clear.db"

        first = Database(path)
        store = AvailableTimeStore(first)
        store.set(plan_date, 195)
        store.clear(plan_date)
        first.close()

        second = Database(path)
        try:
            assert AvailableTimeStore(second).get(plan_date) is None
        finally:
            second.close()


class TestCorruptData:
    @pytest.mark.parametrize("raw", [
        "not json",
        "",
        "[]",
        "null",
        "123",
        '"a string"',
        '{"2026-08-16": "ninety"}',
        '{"2026-08-16": null}',
        '{"2026-08-16": 12.5}',
        '{"2026-08-16": true}',
        '{"not-a-date": 90}',
        '{"2026-08-16": -5}',
        '{"2026-08-16": 99999}',
    ])
    def test_unusable_values_read_as_no_data(
        self, database, plan_date, raw
    ):
        database.set_setting(SETTING_KEY, raw)
        store = AvailableTimeStore(database)

        assert store.get(plan_date) is None
        assert store.get("2026-08-16") is None

    def test_corrupt_json_does_not_raise_on_write(
        self, database, plan_date
    ):
        database.set_setting(SETTING_KEY, "not json")
        store = AvailableTimeStore(database)

        store.set(plan_date, 120)

        assert store.get(plan_date) == 120

    def test_valid_entries_survive_alongside_invalid_ones(
        self, database, plan_date
    ):
        database.set_setting(
            SETTING_KEY,
            json.dumps({plan_date: 120, "nonsense": 90}),
        )
        store = AvailableTimeStore(database)

        assert store.get(plan_date) == 120

    def test_unreadable_database_reads_as_no_data(self, plan_date):
        class BrokenDatabase:
            def get_setting(self, key):
                raise sqlite3.OperationalError("no such table: settings")

        assert AvailableTimeStore(BrokenDatabase()).get(plan_date) is None

    def test_invalid_date_is_never_written(self, store, database):
        assert store.set("not-a-date", 120) is None
        assert database.get_setting(SETTING_KEY) is None


class TestRetention:
    def test_old_entries_are_pruned_on_write(
        self, store, database, plan_date
    ):
        from datetime import date, timedelta

        stale = (date.today() - timedelta(days=90)).isoformat()
        database.set_setting(SETTING_KEY, json.dumps({stale: 120}))

        store.set(plan_date, 180)
        decoded = json.loads(database.get_setting(SETTING_KEY))

        assert stale not in decoded
        assert decoded[plan_date] == 180

    def test_far_future_entries_are_pruned(
        self, store, database, plan_date
    ):
        from datetime import date, timedelta

        distant = (date.today() + timedelta(days=365)).isoformat()
        database.set_setting(SETTING_KEY, json.dumps({distant: 120}))

        store.set(plan_date, 180)
        decoded = json.loads(database.get_setting(SETTING_KEY))

        assert distant not in decoded

    def test_recent_entries_are_kept(self, store, database, plan_date):
        from datetime import date, timedelta

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        database.set_setting(SETTING_KEY, json.dumps({yesterday: 120}))

        store.set(plan_date, 180)
        decoded = json.loads(database.get_setting(SETTING_KEY))

        assert decoded[yesterday] == 120
        assert decoded[plan_date] == 180

    def test_the_written_date_is_never_pruned(self, store, database):
        from datetime import date, timedelta

        distant = (date.today() + timedelta(days=365)).isoformat()

        store.set(distant, 180)

        assert store.get(distant) == 180


class TestDatabaseSafety:
    def test_daily_goal_is_untouched(self, store, database, plan_date):
        original = database.get_daily_goal()

        store.set(plan_date, 180)
        store.clear(plan_date)

        assert database.get_daily_goal() == original
        assert database.get_setting("daily_goal") == str(original)

    def test_total_xp_is_untouched(self, store, database, plan_date):
        database.set_setting("total_xp", "540")

        store.set(plan_date, 180)

        assert database.get_setting("total_xp") == "540"

    def test_only_one_settings_key_is_added(
        self, store, database, plan_date
    ):
        database.cursor.execute("SELECT key FROM settings")
        before = {row[0] for row in database.cursor.fetchall()}

        store.set(plan_date, 180)

        database.cursor.execute("SELECT key FROM settings")
        after = {row[0] for row in database.cursor.fetchall()}

        assert after - before == {SETTING_KEY}

    def test_schema_version_is_unchanged(
        self, store, database, plan_date
    ):
        store.set(plan_date, 180)

        database.cursor.execute("PRAGMA user_version")
        assert database.cursor.fetchone()[0] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 3

    def test_no_new_tables_are_created(self, store, database, plan_date):
        database.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        before = {row[0] for row in database.cursor.fetchall()}

        store.set(plan_date, 180)

        database.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        after = {row[0] for row in database.cursor.fetchall()}

        assert before == after

    def test_activities_are_untouched(self, store, database, plan_date):
        from Modules.activity import Activity

        database.add_activity(Activity(
            id=None,
            date=plan_date,
            activity_type="Coding",
            name="Project",
            estimated_minutes=60,
        ))
        database.cursor.execute("SELECT * FROM activities ORDER BY id")
        before = database.cursor.fetchall()

        store.set(plan_date, 180)
        store.clear(plan_date)

        database.cursor.execute("SELECT * FROM activities ORDER BY id")
        assert database.cursor.fetchall() == before
