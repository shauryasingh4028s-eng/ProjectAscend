"""InsightsService v1.3 additions: periods, distributions, rhythm,
highlights and evidence-backed learned insights.

All tests use temporary databases; the real user database is never
touched. Existing v1.2 analytics behaviour is covered by the rest of the
suite - these tests only assert the new capabilities and their empty /
insufficient-data states.
"""

from datetime import date, datetime, time, timedelta

import pytest

from Database.database import Database
from Modules.activity import Activity
from Modules.insights_service import InsightsService
from Modules.streak_manager import StreakManager


@pytest.fixture
def service(tmp_path):
    db = Database(tmp_path / "insights.db")
    yield InsightsService(db, StreakManager(db))
    db.close()


def add_activity(db, activity_date, activity_type, name, estimated, actual=None, completed=None):
    activity = Activity(
        id=None,
        date=activity_date,
        activity_type=activity_type,
        name=name,
        estimated_minutes=estimated,
    )
    db.add_activity(activity)
    if completed is not None:
        loaded = db.get_activities_for_date(activity_date)[-1]
        loaded.completed = completed
        loaded.actual_minutes = actual or 0
        db.update_activity(loaded)
    return activity


def add_session(db, session_date, hour, minutes, activity_id=1):
    """Persist a focus session dated exactly on ``session_date``.

    The production path (``record_focus_session``) stamps ``session_date``
    with the day the session was RECORDED (the machine clock). This
    fixture therefore writes the column explicitly so a seeded session is
    persisted exactly as the app would on that day, regardless of the
    machine clock - the same columns and values, same table.
    """
    started = datetime.combine(session_date, time(hour, 0))
    completed = started + timedelta(minutes=minutes)
    db.connection.execute(
        """
        INSERT INTO focus_sessions (
            activity_id,
            session_date,
            started_at,
            completed_at,
            actual_minutes,
            actual_seconds
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            session_date.isoformat(),
            started.isoformat(timespec="seconds"),
            completed.isoformat(timespec="seconds"),
            minutes,
            minutes * 60,
        ),
    )
    db.connection.commit()


class TestRangeDefinitions:
    def test_90_days_range(self, service):
        today = date(2026, 8, 14)
        definition = service.get_range_definition("90_days", today)
        assert definition.label == "3 Months"
        assert definition.start_date == date(2026, 5, 17)
        assert definition.previous_start_date == date(2026, 2, 16)

    def test_all_time_range_starts_at_earliest_data(self, service, tmp_path):
        db = service.database
        add_activity(db, "2026-03-01", "Coding", "Old", 30, actual=40, completed=True)
        add_activity(db, "2026-07-01", "Coding", "New", 30, actual=35, completed=True)

        today = date(2026, 8, 14)
        definition = service.get_range_definition("all_time", today)
        assert definition.start_date == date(2026, 3, 1)
        assert definition.previous_start_date is None

    def test_all_time_has_no_previous_comparison(self, service, tmp_path):
        db = service.database
        add_activity(db, "2026-03-01", "Coding", "Old", 30, actual=40, completed=True)
        data = service.build_dashboard("all_time", today=date(2026, 8, 14))
        assert data.overview.focus_change_percent is None
        assert data.overview.activity_change is None
        assert data.trend.comparison.previous_focus_minutes == 0


class TestOverviewDeltas:
    def test_comparison_deltas_are_computed(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        # Previous 30 days: 50 focus minutes, 2 of 3 completed.
        add_activity(db, "2026-07-01", "Study", "A", 60, actual=50, completed=True)
        add_activity(db, "2026-07-01", "Study", "B", 60, actual=0, completed=False)
        add_activity(db, "2026-07-02", "Study", "C", 60, actual=40, completed=True)
        # Current 30 days: 100 focus minutes, 3 of 3 completed.
        add_activity(db, "2026-08-01", "Coding", "D", 60, actual=60, completed=True)
        add_activity(db, "2026-08-02", "Coding", "E", 60, actual=40, completed=True)
        add_activity(db, "2026-08-03", "Coding", "F", 60, actual=0, completed=False)

        data = service.build_dashboard("30_days", today=today)
        overview = data.overview
        # Current period: 100 focus minutes (60 + 40), 2 of 3 completed.
        # Previous period: 90 focus minutes (50 + 40), 2 of 3 completed.
        assert overview.focus_minutes == 100
        assert overview.focus_change_percent == 11  # (100 - 90) / 90
        assert overview.completion_rate == 67       # 2 of 3
        assert overview.previous_completion_rate == 67
        assert overview.completion_change_points == 0
        assert overview.activity_change == 0        # 2 completed vs 2
        assert overview.active_days == 2            # 08-03 had no completed work

    def test_no_deltas_without_previous_data(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        add_activity(db, "2026-08-10", "Coding", "A", 60, actual=45, completed=True)
        data = service.build_dashboard("7_days", today=today)
        assert data.overview.focus_change_percent is None
        assert data.overview.completion_change_points is None
        assert data.overview.activity_change is None


class TestActivityDistribution:
    def test_ranked_shares_sum_to_100(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14).isoformat()
        for category, minutes in (
            ("Coding", 300),
            ("Study", 200),
            ("Homework", 100),
            ("Reading", 40),
        ):
            add_activity(db, today, category, category, 30, actual=minutes, completed=True)

        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        items = data.distribution.items
        assert [item.category for item in items] == [
            "Coding",
            "Study",
            "Homework",
            "Reading",
        ]
        assert sum(item.percent for item in items) == 100
        assert data.distribution.total_minutes == 640

    def test_extra_categories_merge_into_other(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14).isoformat()
        for index in range(9):
            add_activity(
                db,
                today,
                f"Category {index}",
                f"task {index}",
                30,
                actual=30,
                completed=True,
            )

        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        items = data.distribution.items
        assert len(items) == 7  # 6 visible + Other
        assert items[-1].category == "Other"
        assert sum(item.percent for item in items) == 100

    def test_empty_distribution(self, service):
        data = service.build_dashboard("30_days")
        assert data.distribution.items == ()
        assert data.distribution.total_minutes == 0


class TestDayHourPattern:
    def test_learning_state_with_few_sessions(self, service, tmp_path):
        db = service.database
        add_session(db, date(2026, 8, 10), 18, 40)
        add_session(db, date(2026, 8, 11), 9, 30)

        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        pattern = data.day_hour
        assert pattern.total_sessions == 2
        assert pattern.status == "learning"
        assert pattern.strongest_window_label is not None  # computed but not claimed

    def test_ready_state_with_enough_sessions(self, service, tmp_path):
        db = service.database
        # 10 evening sessions: 7 fall inside the 6-8 PM window.
        for index in range(10):
            hour = 18 if index < 7 else (9 if index < 9 else 13)
            add_session(db, date(2026, 8, 1 + index), hour, 40)

        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        pattern = data.day_hour
        assert pattern.status == "ready"
        assert pattern.strongest_window_label is not None
        assert pattern.window_session_count >= 3

    def test_empty_state(self, service):
        data = service.build_dashboard("30_days")
        assert data.day_hour.status == "empty"
        assert data.day_hour.strongest_window_label is None

    def test_morning_afternoon_evening_night_blocks(self, service, tmp_path):
        db = service.database
        add_session(db, date(2026, 8, 10), 8, 30)   # morning
        add_session(db, date(2026, 8, 10), 14, 30)  # afternoon
        add_session(db, date(2026, 8, 10), 19, 30)  # evening
        add_session(db, date(2026, 8, 10), 23, 30)  # night

        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        cells = data.day_hour.cells
        blocks = {cell.block_index: cell for cell in cells}
        assert set(blocks) == {0, 1, 2, 3}
        # Monday = weekday index 0.
        assert blocks[0].day_index == 0
        assert blocks[3].session_count == 1


class TestHighlights:
    def test_highlights_from_real_data(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        # Previous period so an improvement exists.
        add_activity(db, "2026-07-01", "Study", "Old", 60, actual=30, completed=True)
        add_activity(db, "2026-08-01", "Coding", "A", 60, actual=60, completed=True)
        add_session(db, today, 10, 90)
        add_session(db, today - timedelta(days=1), 15, 45)

        data = service.build_dashboard("30_days", today=today)
        highlights = data.highlights
        assert highlights.best_day is not None
        assert highlights.longest_session is not None
        assert highlights.longest_session.value == "1h 30m"
        assert highlights.improvement is not None  # 105 vs 30 minutes

    def test_highlights_empty_state(self, service):
        data = service.build_dashboard("30_days")
        assert data.highlights.best_day is None
        assert data.highlights.longest_session is None
        assert data.highlights.improvement is None


class TestLearnedInsights:
    def test_no_insights_without_evidence(self, service, tmp_path):
        db = service.database
        add_activity(db, "2026-08-10", "Coding", "A", 30, actual=35, completed=True)
        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        assert data.learned == ()

    def test_rhythm_insight_only_when_ready(self, service, tmp_path):
        db = service.database
        for index in range(10):
            add_session(db, date(2026, 8, 1 + index), 18, 40)
        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        titles = [insight.title for insight in data.learned]
        assert "Focus Window" in titles
        window = next(i for i in data.learned if i.title == "Focus Window")
        assert window.evidence.startswith("Based on")
        assert window.confidence in ("moderate_confidence", "high_confidence")

    def test_category_bias_insight_requires_samples(self, service, tmp_path):
        db = service.database
        # 6 Homework activities, all underestimates (take longer than planned).
        for index in range(6):
            add_activity(
                db,
                f"2026-08-{index + 1:02d}",
                "Homework",
                f"hw {index}",
                30,
                actual=45,
                completed=True,
            )
        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        titles = [insight.title for insight in data.learned]
        assert "Estimate Pattern" in titles
        pattern = next(i for i in data.learned if i.title == "Estimate Pattern")
        assert "underestimate" in pattern.description
        assert "6 completed activities" in pattern.evidence

    def test_category_bias_ignored_with_tiny_samples(self, service, tmp_path):
        db = service.database
        for index in range(2):
            add_activity(
                db,
                f"2026-08-{index + 1:02d}",
                "Homework",
                f"hw {index}",
                30,
                actual=60,
                completed=True,
            )
        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        assert all(i.title != "Estimate Pattern" for i in data.learned)

    def test_planning_improvement_insight(self, service, tmp_path):
        db = service.database
        # Older activities: poor estimates. Newer: accurate estimates.
        for index in range(5):
            add_activity(
                db,
                f"2026-07-0{index + 1}",
                "Maths",
                f"old {index}",
                60,
                actual=120,
                completed=True,
            )
        for index in range(5):
            add_activity(
                db,
                f"2026-08-0{index + 1}",
                "Maths",
                f"new {index}",
                60,
                actual=62,
                completed=True,
            )
        data = service.build_dashboard("30_days", today=date(2026, 8, 14))
        titles = [insight.title for insight in data.learned]
        assert "Sharper Estimates" in titles

    def test_learned_insights_capped_at_four(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        # Build a rich dataset: rhythm + category + day + consistency.
        for index in range(10):
            add_session(db, today - timedelta(days=index), 18, 40)
        for index in range(6):
            add_activity(
                db,
                f"2026-08-{index + 1:02d}",
                "Homework",
                f"hw {index}",
                30,
                actual=45,
                completed=True,
            )
        for index in range(10):
            add_activity(
                db,
                f"2026-08-{min(index + 1, 12):02d}",
                "Coding",
                f"c {index}",
                60,
                actual=55,
                completed=True,
            )
        data = service.build_dashboard("30_days", today=today)
        assert 0 < len(data.learned) <= 4


class TestTrendAggregation:
    def test_long_range_buckets_to_weekly(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        for offset in range(0, 90, 3):
            add_activity(
                db,
                (today - timedelta(days=offset)).isoformat(),
                "Coding",
                f"task {offset}",
                30,
                actual=25,
                completed=True,
            )
        data = service.build_dashboard("90_days", today=today)
        assert data.trend.granularity == "weekly"
        assert len(data.trend.points) <= 14
        assert data.trend.total_focus_minutes > 0

    def test_short_range_stays_daily(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        add_activity(
            db,
            today.isoformat(),
            "Coding",
            "task",
            30,
            actual=25,
            completed=True,
        )
        data = service.build_dashboard("7_days", today=today)
        assert data.trend.granularity == "daily"
        assert len(data.trend.points) == 7

    def test_all_time_aggregates_long_spans(self, service, tmp_path):
        db = service.database
        today = date(2026, 8, 14)
        for offset in range(0, 400, 5):
            add_activity(
                db,
                (today - timedelta(days=offset)).isoformat(),
                "Coding",
                f"task {offset}",
                30,
                actual=25,
                completed=True,
            )
        data = service.build_dashboard("all_time", today=today)
        assert data.trend.granularity == "monthly"
        assert len(data.trend.points) <= 15


class TestEmptyDashboard:
    def test_empty_database_builds_safely(self, service):
        data = service.build_dashboard("7_days")
        assert data.overview.focus_minutes == 0
        assert data.distribution.items == ()
        assert data.day_hour.status == "empty"
        assert data.highlights.best_day is None
        assert data.learned == ()
        assert data.calibration.summary.evidence_level == "insufficient_data"
