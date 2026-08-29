"""Tests for Database Schema Migration v3 and Progression Persistence API."""

import sqlite3
import pytest
from datetime import date
from Database.database import Database, SCHEMA_VERSION


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_ascend.db"
    db = Database(str(db_path))
    yield db
    db.close()


class TestDatabaseMigrationV3:
    def test_schema_version_is_v3(self, temp_db):
        assert temp_db.get_schema_version() == 3

    def test_v3_tables_created(self, temp_db):
        cursor = temp_db.cursor
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "activities",
            "settings",
            "focus_sessions",
            "xp_events",
            "daily_history",
            "user_achievements",
            "user_progression_profile",
            "level_history",
            "milestone_history",
        }
        assert expected_tables.issubset(tables)

    def test_v3_migration_idempotent(self, temp_db):
        # Running migrations again on a v3 database must be safe and idempotent
        temp_db.run_migrations()
        assert temp_db.get_schema_version() == 3

    def test_achievement_persistence_api(self, temp_db):
        assert temp_db.get_unlocked_achievements() == []

        success = temp_db.unlock_achievement("consistency_first_step", trigger_event="manual")
        assert success is True

        # Duplicate unlock should be ignored (returns False or doesn't add duplicate row)
        duplicate = temp_db.unlock_achievement("consistency_first_step", trigger_event="manual")
        assert duplicate is False

        unlocked = temp_db.get_unlocked_achievements()
        assert len(unlocked) == 1
        assert unlocked[0]["achievement_id"] == "consistency_first_step"
        assert unlocked[0]["trigger_event"] == "manual"

    def test_progression_profile_api(self, temp_db):
        assert temp_db.get_progression_setting("selected_character_id") is None
        temp_db.set_progression_setting("selected_character_id", "catalyst")
        assert temp_db.get_progression_setting("selected_character_id") == "catalyst"

    def test_milestone_history_api(self, temp_db):
        assert temp_db.get_milestone_history() == []

        res1 = temp_db.record_milestone_reach("focus_duration", tier=1)
        assert res1 is True

        res2 = temp_db.record_milestone_reach("focus_duration", tier=1)
        assert res2 is False

        history = temp_db.get_milestone_history()
        assert len(history) == 1
        assert history[0]["milestone_id"] == "focus_duration"
        assert history[0]["tier"] == 1
