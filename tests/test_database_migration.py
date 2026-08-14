"""Database migration safety: v1.1 and legacy databases must reach the
v1.2 schema with every existing value preserved, and the migration must be
repeatable. All tests use temporary databases; the real database is never
touched.
"""

import sqlite3

from Database.database import SCHEMA_VERSION, Database
from Modules.activity import Activity


def read_rows(path, table):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    connection.close()
    return rows


class TestV1ToV2Migration:
    def test_v1_1_database_migrates_safely(self, v1_1_database_path):
        before = read_rows(v1_1_database_path, "activities")

        db = Database(v1_1_database_path)
        db.close()

        after = read_rows(v1_1_database_path, "activities")

        # Every existing row keeps its id and every existing value.
        assert len(after) == len(before)
        for before_row, after_row in zip(before, after):
            assert after_row["id"] == before_row["id"]
            assert after_row["date"] == before_row["date"]
            assert after_row["activity_type"] == before_row["activity_type"]
            assert after_row["name"] == before_row["name"]
            assert after_row["estimated_minutes"] == before_row["estimated_minutes"]
            assert after_row["completed"] == before_row["completed"]
            assert after_row["actual_minutes"] == before_row["actual_minutes"]
            assert after_row["xp_awarded"] == before_row["xp_awarded"]

        # The new column exists and is backfilled from the current estimate
        # (the best available original for pre-v1.2 records).
        for after_row in after:
            assert after_row["original_estimate_minutes"] == after_row["estimated_minutes"]

    def test_focus_sessions_get_actual_seconds_column(self, v1_1_database_path):
        db = Database(v1_1_database_path)
        sessions = db.get_insights_records("2020-01-01", "2030-01-01")["focus_sessions"]
        db.close()

        connection = sqlite3.connect(v1_1_database_path)
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(focus_sessions)")
        ]
        connection.close()

        assert "actual_seconds" in columns
        # Existing sessions keep their minute-level value; seconds are NULL
        # because they were never recorded.
        assert len(sessions) == 1
        assert sessions[0]["actual_minutes"] == 150

    def test_settings_and_xp_preserved(self, v1_1_database_path):
        db = Database(v1_1_database_path)
        assert db.get_setting("total_xp") == "540"
        assert db.get_setting("daily_goal") == "210"
        assert db.get_total_xp_setting() == 540
        db.close()

    def test_schema_version_recorded(self, v1_1_database_path):
        db = Database(v1_1_database_path)
        assert db.get_schema_version() == SCHEMA_VERSION
        db.close()

    def test_migration_is_repeatable(self, v1_1_database_path):
        # Opening the database again must be a no-op, not a re-migration.
        first = Database(v1_1_database_path)
        first.close()
        rows_after_first = read_rows(v1_1_database_path, "activities")

        second = Database(v1_1_database_path)
        assert second.get_schema_version() == SCHEMA_VERSION
        second.close()
        rows_after_second = read_rows(v1_1_database_path, "activities")

        assert rows_after_first == rows_after_second

    def test_daily_history_rebuilt_from_activities(self, v1_1_database_path):
        db = Database(v1_1_database_path)
        history = db.get_daily_history()
        db.close()
        dates = {row[1] for row in history}
        assert "2026-07-01" in dates


class TestLegacyV0Migration:
    def test_v0_database_upgrades_through_v1_1_to_v1_2(self, v0_database_path):
        db = Database(v0_database_path)

        # Legacy columns were added by the v1.1 compatibility layer.
        connection = sqlite3.connect(v0_database_path)
        activity_columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(activities)")
        ]
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        connection.close()

        for column in ("date", "actual_minutes", "xp_awarded", "original_estimate_minutes"):
            assert column in activity_columns
        for table in ("focus_sessions", "xp_events", "daily_history"):
            assert table in table_names
        # The obsolete legacy table is left exactly as it was.
        assert "tasks" in table_names

        assert db.get_schema_version() == SCHEMA_VERSION
        # Legacy values survive.
        assert db.get_setting("total_xp") == "540"
        assert db.get_setting("daily_goal") == "210"

        activities = db.get_activities()
        assert len(activities) == 2
        assert activities[0].name == "NCERT"
        assert activities[0].actual_minutes == 35
        assert activities[0].original_estimate_minutes == 30
        assert activities[1].completed is False

        tasks = read_rows(v0_database_path, "tasks")
        assert len(tasks) == 1
        assert tasks[0]["name"] == "old"
        db.close()


class TestFreshInstall:
    def test_fresh_database_gets_full_schema(self, tmp_path):
        path = tmp_path / "brand_new.db"
        db = Database(path)
        assert db.get_schema_version() == SCHEMA_VERSION
        assert db.get_daily_goal() == 360
        db.close()

    def test_fresh_database_accepts_new_fields(self, tmp_path):
        path = tmp_path / "brand_new.db"
        db = Database(path)
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="Fresh task",
            estimated_minutes=60,
        )
        db.add_activity(activity)
        loaded = db.get_activities_for_date("2026-08-14")[0]
        assert loaded.id is not None
        assert loaded.original_estimate_minutes == 60
        db.close()


class TestOriginalEstimateSemantics:
    def test_original_estimate_set_at_creation(self, database):
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="Plan",
            estimated_minutes=45,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date("2026-08-14")[0]
        assert loaded.original_estimate_minutes == 45

    def test_edit_before_work_updates_original(self, database):
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="Plan",
            estimated_minutes=30,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date("2026-08-14")[0]

        loaded.estimated_minutes = 60
        database.update_activity(loaded)
        refreshed = database.get_activities_for_date("2026-08-14")[0]
        assert refreshed.estimated_minutes == 60
        assert refreshed.original_estimate_minutes == 60

    def test_edit_after_focus_session_preserves_original(self, database):
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="Plan",
            estimated_minutes=60,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date("2026-08-14")[0]

        # A recorded focus session means work happened.
        database.record_focus_session(
            loaded.id,
            "2026-08-14T10:00:00",
            "2026-08-14T11:30:00",
            90,
            actual_seconds=5400,
        )

        loaded.estimated_minutes = 120
        database.update_activity(loaded)
        refreshed = database.get_activities_for_date("2026-08-14")[0]
        assert refreshed.estimated_minutes == 120
        assert refreshed.original_estimate_minutes == 60

    def test_edit_after_completion_preserves_original(self, database):
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="Plan",
            estimated_minutes=60,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date("2026-08-14")[0]

        loaded.completed = True
        loaded.actual_minutes = 95
        database.update_activity(loaded)

        loaded.estimated_minutes = 200
        database.update_activity(loaded)
        refreshed = database.get_activities_for_date("2026-08-14")[0]
        assert refreshed.estimated_minutes == 200
        assert refreshed.original_estimate_minutes == 60
        assert refreshed.completed is True
        assert refreshed.actual_minutes == 95
