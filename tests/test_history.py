"""Tests for the Project Ascend History tab rework (Concept C Dual-Pane & Day Snapshot)."""

import pytest
from datetime import date, timedelta
from PySide6.QtCore import Qt

from Database.database import Database
from Modules.history import (
    HistoryWindow,
    HistoryDayCard,
    DaySnapshotWidget,
    get_recency_group,
)


@pytest.fixture
def history_db(tmp_path):
    db_path = tmp_path / "test_history.db"
    db = Database(str(db_path))

    # Add sample activity and daily history data
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    db.cursor.execute(
        "INSERT INTO activities (date, activity_type, name, estimated_minutes, completed, actual_minutes, xp_awarded) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (today_str, "Study", "Math Revision", 30, 1, 30, 50),
    )
    db.cursor.execute(
        "INSERT INTO activities (date, activity_type, name, estimated_minutes, completed, actual_minutes, xp_awarded) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (today_str, "Study", "Chemistry Notes", 45, 1, 45, 60),
    )
    db.cursor.execute(
        "INSERT INTO focus_sessions (activity_id, session_date, started_at, completed_at, actual_minutes) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, today_str, "09:00", "09:30", 30),
    )
    db.cursor.execute(
        "INSERT INTO xp_events (activity_id, earned_date, amount, event_type) "
        "VALUES (?, ?, ?, ?)",
        (1, today_str, 50, "activity_completion"),
    )
    db.cursor.execute(
        "INSERT INTO xp_events (activity_id, earned_date, amount, event_type) "
        "VALUES (?, ?, ?, ?)",
        (2, today_str, 60, "activity_completion"),
    )

    db.update_daily_history(today_str)
    db.update_daily_history(yesterday_str)

    yield db
    db.close()


def test_recency_group_calculation():
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert get_recency_group(today) == "THIS WEEK"
    assert get_recency_group("invalid_date") == "EARLIER HISTORY"


def test_database_get_day_details(history_db):
    today_str = date.today().isoformat()
    details = history_db.get_day_details(today_str)

    assert details["date"] == today_str
    assert details["history"] is not None
    assert len(details["activities"]) == 2
    assert len(details["focus_sessions"]) == 1
    assert details["total_xp"] == 110
    assert details["daily_goal"] == 360


def test_history_window_build_and_load(qapp, history_db):
    window = HistoryWindow(history_db)
    window.resize(1280, 800)
    window.show()

    assert window.windowTitle() == "Project Ascend - History"
    assert len(window.history_cards) == 2
    assert window.selected_date == date.today().isoformat()

    # Verify inspector has populated details for selected day
    assert window.inspector_snapshot.current_date == date.today().isoformat()
    assert window.inspector_snapshot.tile_focus.val_lbl.text() == "1h 15m"
    window.close()


def test_history_day_selection(qapp, history_db):
    window = HistoryWindow(history_db)
    window.resize(1280, 800)
    window.show()

    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    yesterday_card = window.history_cards[yesterday_str]

    # Click yesterday's card
    yesterday_card.clicked.emit(yesterday_str)

    assert window.selected_date == yesterday_str
    assert yesterday_card.selected is True
    assert window.inspector_snapshot.current_date == yesterday_str
    window.close()


def test_history_responsive_views_and_rapid_clicks(qapp, history_db):
    window = HistoryWindow(history_db)

    # Test wide layout (>=1180px)
    window.resize(1280, 800)
    window.show()
    assert window.inspector_container.isVisible() is True
    assert window.rail_container.isVisible() is True

    # Test compact layout (<1180px)
    window.resize(1000, 700)
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    window.select_day(today_str)
    assert window.inspector_container.isVisible() is True
    assert window.rail_container.isVisible() is False

    # Close inspector in compact mode
    window._handle_inspector_closed()
    assert window.inspector_container.isVisible() is False
    assert window.rail_container.isVisible() is True

    # Rapid day switches
    for _ in range(10):
        window.select_day(yesterday_str)
        window.select_day(today_str)

    window.close()


def test_history_empty_state(qapp, tmp_path):
    empty_db = Database(str(tmp_path / "empty.db"))
    window = HistoryWindow(empty_db)
    window.show()

    assert len(window.history_cards) == 0
    assert window.empty_state.isVisible() is True
    assert window.rail_scroll.isVisible() is False
    window.close()
    empty_db.close()
