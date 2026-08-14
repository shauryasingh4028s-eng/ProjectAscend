"""Shared fixtures for the Project Ascend test suite.

All database fixtures build SEPARATE temporary SQLite files under pytest's
tmp_path. The real user database (and its checked-in copy) is never opened
for writing by tests; the real-data test copies the checked-in file first.
"""

import sqlite3

import pytest


@pytest.fixture(scope="session")
def qapp():
    """One shared QApplication for Qt-based tests, running offscreen."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def create_legacy_v0_database(path):
    """Build a v0.x-era database: old activities columns plus a `tasks`
    table, exactly like the checked-in legacy copy that predates v1.1."""
    connection = sqlite3.connect(path)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            estimated_minutes INTEGER,
            actual_minutes INTEGER,
            completed INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            estimated_minutes INTEGER NOT NULL,
            completed INTEGER DEFAULT 0,
            date TEXT DEFAULT '',
            actual_minutes INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cursor.execute(
        "INSERT INTO activities "
        "(activity_type, name, estimated_minutes, completed, date, actual_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Homework", "NCERT", 30, 1, "2026-07-01", 35),
    )
    cursor.execute(
        "INSERT INTO activities "
        "(activity_type, name, estimated_minutes, completed, date, actual_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Coding", "Project", 60, 0, "2026-07-01", 0),
    )
    cursor.execute("INSERT INTO tasks (name, category) VALUES (?, ?)", ("old", "legacy"))
    cursor.execute("INSERT INTO settings (key, value) VALUES ('total_xp', '540')")
    cursor.execute("INSERT INTO settings (key, value) VALUES ('daily_goal', '210')")
    connection.commit()
    connection.close()


def create_v1_1_database(path):
    """Build a database with the exact v1.1 schema and sample data.

    This mirrors what a real v1.1 installation has: no
    original_estimate_minutes, no actual_seconds, user_version = 0.
    """
    connection = sqlite3.connect(path)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            estimated_minutes INTEGER NOT NULL,
            completed INTEGER DEFAULT 0,
            actual_minutes INTEGER DEFAULT 0,
            xp_awarded INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER,
            session_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            actual_minutes INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE xp_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER,
            earned_date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            UNIQUE(activity_id, event_type)
        )
    """)
    cursor.execute("""
        CREATE TABLE daily_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            study_minutes INTEGER NOT NULL DEFAULT 0,
            completed_activities INTEGER NOT NULL DEFAULT 0,
            total_activities INTEGER NOT NULL DEFAULT 0,
            goal_completed INTEGER NOT NULL DEFAULT 0
        )
    """)

    sample = [
        # (date, type, name, estimate, completed, actual, xp_awarded)
        ("2026-07-01", "Coding", "API", 120, 1, 150, 1),
        ("2026-07-01", "Coding", "UI", 90, 1, 75, 1),
        ("2026-07-01", "Study", "Revision", 60, 1, 60, 1),
        ("2026-07-02", "Coding", "Tests", 30, 0, 0, 0),
        ("2026-07-02", "Study", "Homework", 45, 1, 20, 1),
    ]
    for index, row in enumerate(sample, start=1):
        cursor.execute(
            "INSERT INTO activities "
            "(id, date, activity_type, name, estimated_minutes, completed, "
            " actual_minutes, xp_awarded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (index,) + row,
        )

    cursor.execute(
        "INSERT INTO focus_sessions "
        "(activity_id, session_date, started_at, completed_at, actual_minutes) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "2026-07-01", "10:00:00", "12:30:00", 150),
    )
    cursor.execute(
        "INSERT INTO xp_events "
        "(activity_id, earned_date, amount, event_type) "
        "VALUES (?, ?, ?, ?)",
        (1, "2026-07-01", 10, "activity_completion"),
    )
    cursor.execute(
        "INSERT INTO settings (key, value) VALUES ('total_xp', '540')"
    )
    cursor.execute(
        "INSERT INTO settings (key, value) VALUES ('daily_goal', '210')"
    )
    cursor.execute(
        "INSERT INTO daily_history "
        "(date, study_minutes, completed_activities, total_activities, goal_completed) "
        "VALUES (?, ?, ?, ?, ?)",
        ("2026-07-01", 285, 3, 3, 1),
    )
    connection.commit()
    connection.close()


@pytest.fixture
def v0_database_path(tmp_path):
    path = tmp_path / "legacy_v0.db"
    create_legacy_v0_database(path)
    return path


@pytest.fixture
def v1_1_database_path(tmp_path):
    path = tmp_path / "v1_1.db"
    create_v1_1_database(path)
    return path


@pytest.fixture
def real_data_database_path(tmp_path):
    """A COPY of the checked-in legacy user database, never the original."""
    import shutil

    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    source = repo_root / "Database" / "ascend.db"
    if not source.exists():
        pytest.skip("checked-in Database/ascend.db fixture not present")
    destination = tmp_path / "real_data_copy.db"
    shutil.copy2(source, destination)
    return destination


@pytest.fixture
def database(tmp_path):
    """A fresh, empty database in a temporary location."""
    from Database.database import Database

    db = Database(tmp_path / "fresh.db")
    yield db
    db.close()
