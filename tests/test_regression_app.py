"""End-to-end regression: the full application shell starts, every major
screen renders, a real session flows through the dashboard into the
database, and the Insights page shows the calibration section.

The user's real database location (%LOCALAPPDATA%) is redirected to a
temporary directory so this test can never touch real user data.
"""

import os
from datetime import date

import pytest


@pytest.fixture
def app_controller(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv(
        "LOCALAPPDATA", str(tmp_path / "appdata")
    )
    from Modules.app_controller import AppController

    controller = AppController()
    yield controller
    controller.close_database()


class TestApplicationRegression:
    def test_all_major_screens_construct_and_switch(self, app_controller):
        controller = app_controller
        controller.show_dashboard()
        assert controller.shell.current_page_key() == "dashboard"

        for page_key in ("planner", "insights", "history", "progress", "settings"):
            controller.shell.show_page(page_key)
            assert controller.shell.current_page_key() == page_key
        # Insights must have rendered real data, including calibration.
        assert controller.analytics_window.dashboard_data is not None
        controller.show_dashboard()

    def test_full_session_flow_and_insights_calibration(self, app_controller):
        controller = app_controller
        database = controller.database
        today = date.today().isoformat()

        from Modules.activity import Activity

        database.add_activity(
            Activity(
                id=None,
                date=today,
                activity_type="Coding",
                name="End to end",
                estimated_minutes=60,
            )
        )
        # A second, unfinished activity keeps the completion flow from
        # opening the modal "all done" congratulation dialog.
        database.add_activity(
            Activity(
                id=None,
                date=today,
                activity_type="Study",
                name="Still open",
                estimated_minutes=30,
            )
        )
        loaded = database.get_activities_for_date(today)[0]

        engine = controller.dashboard.session_engine
        engine.start(loaded)
        engine.elapsed_seconds = 3661
        engine.complete()

        # XP was awarded exactly once for the completed activity.
        assert database.get_total_xp_setting() == 10

        # The dashboard shows the completed activity.
        controller.dashboard.load_today_activities()
        visible = database.get_activities_for_date(today)[0]
        assert visible.completed is True
        assert visible.actual_minutes == 62

        # Insights renders the calibration section with real observations.
        controller.show_analytics()
        data = controller.analytics_window.dashboard_data
        calibration = data.calibration
        assert calibration.summary.sample_count == 1
        assert calibration.summary.evidence_level == "insufficient_data"
        assert calibration.summary.suggested_multiplier is None
        assert data.overview.completed_tasks >= 1

    def test_calibration_section_renders_without_data(self, app_controller):
        # A brand-new installation must render "not enough data", never an
        # invented number.
        controller = app_controller
        controller.show_analytics()
        data = controller.analytics_window.dashboard_data
        summary = data.calibration.summary
        assert summary.sample_count == 0
        assert summary.evidence_level == "insufficient_data"
        assert summary.suggested_multiplier is None

        card = controller.analytics_window.bias_card
        assert "Not enough data yet" in card.value_label.text()

    def test_restart_with_controller_database(self, tmp_path, monkeypatch, qapp):
        # Simulate an app restart: a fresh controller reads the same
        # database directory and still sees everything.
        appdata = tmp_path / "appdata"
        monkeypatch.setenv("LOCALAPPDATA", str(appdata))

        from Database.database import Database
        from Modules.activity import Activity

        first = Database(appdata / "ProjectAscend" / "Database" / "ascend.db")
        today = date.today().isoformat()
        first.add_activity(
            Activity(
                id=None,
                date=today,
                activity_type="Study",
                name="Persists across restarts",
                estimated_minutes=45,
            )
        )
        first.close()

        from Modules.app_controller import AppController

        controller = AppController()
        try:
            activities = controller.database.get_activities_for_date(today)
            assert len(activities) == 1
            assert activities[0].name == "Persists across restarts"
            controller.show_dashboard()
        finally:
            controller.close_database()
