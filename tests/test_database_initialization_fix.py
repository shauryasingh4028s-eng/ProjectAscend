"""Regression tests for database initialization, level_history creation order, and reconciliation safety."""

import sqlite3
import pytest
from Database.database import Database


def test_fresh_database_initialization_creates_level_history(tmp_path):
    """A. Fresh database initialization creates level_history before reconciliation."""
    db_path = tmp_path / "fresh.db"
    db = Database(str(db_path))

    # Verify level_history table exists immediately on initialization
    db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='level_history'")
    assert db.cursor.fetchone() is not None

    db.close()


def test_existing_database_missing_level_history_repaired_safely(tmp_path):
    """B. Existing database missing level_history (with user_version=3) is repaired safely without error."""
    db_path = tmp_path / "legacy_v3_missing_level_history.db"

    # Simulate an existing database file with user_version=3 but level_history table dropped/missing
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA user_version = 3")
    cur.execute("""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            estimated_minutes INTEGER NOT NULL,
            original_estimate_minutes INTEGER NOT NULL DEFAULT 0,
            completed INTEGER DEFAULT 0,
            actual_minutes INTEGER DEFAULT 0,
            xp_awarded INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)
    """)
    cur.execute("""
        CREATE TABLE xp_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER,
            earned_date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            event_type TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE daily_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            study_minutes INTEGER NOT NULL DEFAULT 0,
            completed_activities INTEGER NOT NULL DEFAULT 0,
            total_activities INTEGER NOT NULL DEFAULT 0,
            goal_completed INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

    # Opening Database on this existing file must repair level_history table and complete startup without crashing
    db = Database(str(db_path))
    db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='level_history'")
    assert db.cursor.fetchone() is not None
    db.close()


def test_database_startup_with_daily_goal_xp_reconciliation(tmp_path):
    """C. Database startup does not crash when XP reconciliation evaluates past completed daily goals."""
    db_path = tmp_path / "daily_goals.db"

    # Pre-populate database with completed daily goals
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA user_version = 3")
    cur.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    cur.execute("""
        CREATE TABLE daily_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            study_minutes INTEGER NOT NULL DEFAULT 120,
            completed_activities INTEGER NOT NULL DEFAULT 2,
            total_activities INTEGER NOT NULL DEFAULT 2,
            goal_completed INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        INSERT INTO daily_history (date, study_minutes, completed_activities, total_activities, goal_completed)
        VALUES ('2026-08-28', 120, 2, 2, 1)
    """)
    conn.commit()
    conn.close()

    # Instantiating Database must perform reconciliation cleanly
    db = Database(str(db_path))
    total_xp = db.get_total_xp_setting()
    assert total_xp >= 50
    db.close()


def test_check_and_record_level_reaches_inserts_level_history(tmp_path):
    """D. check_and_record_level_reaches() safely inserts level history records."""
    db_path = tmp_path / "level_record.db"
    db = Database(str(db_path))

    # Record levels for 250 XP (Level 3)
    # Level 1 is already recorded during DB startup initialization, so newly_recorded returns [2, 3]
    newly_recorded = db.check_and_record_level_reaches(250, timestamp="2026-08-29")
    assert 2 in newly_recorded
    assert 3 in newly_recorded

    history = db.get_level_history()
    levels = [h["level"] for h in history]
    assert 1 in levels
    assert 2 in levels
    assert 3 in levels

    db.close()


def test_level_history_rows_persist_across_reopen(tmp_path):
    """E. Existing level_history rows remain intact after reopening the database."""
    db_path = tmp_path / "persisted_levels.db"
    db1 = Database(str(db_path))
    db1.check_and_record_level_reaches(1000, timestamp="2026-08-29")
    original_history = db1.get_level_history()
    db1.close()

    # Reopen
    db2 = Database(str(db_path))
    reopened_history = db2.get_level_history()
    assert len(reopened_history) == len(original_history)
    assert reopened_history == original_history
    db2.close()


def test_existing_xp_totals_remain_unchanged(tmp_path):
    """F. Existing XP totals remain unchanged after database initialization."""
    db_path = tmp_path / "xp_unchanged.db"
    db1 = Database(str(db_path))
    db1.award_activity_completion_xp(activity_id=1, amount=10)
    initial_total = db1.get_total_xp_setting()
    db1.close()

    # Reopen database multiple times
    db2 = Database(str(db_path))
    reopened_total = db2.get_total_xp_setting()
    assert reopened_total == initial_total
    db2.close()
