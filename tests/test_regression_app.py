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


class TestCalibrationPresentation:
    """Presentation-only checks for the Planning Accuracy section.

    These assert the UI hierarchy (time-first when a recommendation
    exists) without touching any calibration calculation: the displayed
    realistic estimate must equal recommended_estimate() output.
    """

    def complete_seeded_activities(self, database, activity_date):
        for activity in database.get_activities_for_date(activity_date):
            activity.completed = True
            database.update_activity(activity)

    def test_recommendation_state_leads_with_realistic_time(
        self, app_controller
    ):
        controller = app_controller
        database = controller.database
        today = date.today().isoformat()

        from Modules.activity import Activity

        # 12 completed activities, all planned for 60 min and taking 68.
        for index in range(12):
            database.add_activity(
                Activity(
                    id=None,
                    date=today,
                    activity_type="Coding",
                    name=f"Calibration task {index}",
                    estimated_minutes=60,
                )
            )
        for activity in database.get_activities_for_date(today):
            activity.completed = True
            activity.actual_minutes = 68
            database.update_activity(activity)

        controller.show_analytics()
        window = controller.analytics_window
        data = window.dashboard_data
        summary = data.calibration.summary

        # Backend values come straight from the approved engine.
        assert summary.sample_count == 12
        assert summary.suggested_multiplier is not None
        assert summary.evidence_level == "moderate_confidence"

        # The displayed realistic estimate must equal the service's own
        # recommended_estimate(median estimate, multiplier) result.
        from Modules.calibration_service import recommended_estimate

        expected = recommended_estimate(60, summary.suggested_multiplier)
        assert window.bias_card.title_label.text() == "Realistic Estimate"
        assert window.bias_card.value_label.text() == f"~{expected} min"
        assert window.bias_card.detail_label.text() == "For a typical 60-min plan"

        assert (
            window.typical_error_card.title_label.text() == "Time Difference"
        )
        assert window.typical_error_card.value_label.text() == (
            f"+{expected - 60} min"
        )
        assert (
            window.typical_error_card.detail_label.text()
            == "More than your original estimate"
        )

        assert window.confidence_card.value_label.text() == (
            "Moderate confidence"
        )
        assert (
            window.confidence_card.detail_label.text()
            == "Based on 12 completed activities"
        )
        assert (
            "Historical planning factor"
            in window.calibration_note_label.text()
        )

    def test_early_signal_state_never_invents_a_recommendation(
        self, app_controller
    ):
        controller = app_controller
        database = controller.database
        today = date.today().isoformat()

        from Modules.activity import Activity

        # 5 completed activities: statistics exist, but below the
        # recommendation threshold.
        for index in range(5):
            database.add_activity(
                Activity(
                    id=None,
                    date=today,
                    activity_type="Study",
                    name=f"Early task {index}",
                    estimated_minutes=30,
                )
            )
        for activity in database.get_activities_for_date(today):
            activity.completed = True
            activity.actual_minutes = 35
            database.update_activity(activity)

        controller.show_analytics()
        window = controller.analytics_window
        summary = window.dashboard_data.calibration.summary

        assert summary.sample_count == 5
        assert summary.suggested_multiplier is None

        # Standard analytic titles and honest no-recommendation copy.
        assert window.bias_card.title_label.text() == "Estimate Bias"
        assert window.bias_card.value_label.text() == "+17%"
        assert window.typical_error_card.title_label.text() == "Typical Error"
        assert window.confidence_card.value_label.text() == "Early signal"
        assert (
            "no recommendation yet"
            in window.confidence_card.detail_label.text()
        )
        assert (
            "Realistic time suggestions unlock"
            in window.calibration_note_label.text()
        )


class TestInsightsV13:
    """v1.3 Insights Experience: new sections render and stay honest."""

    def test_new_sections_render_with_data(self, app_controller):
        controller = app_controller
        database = controller.database
        today = date.today()

        from Modules.activity import Activity
        from datetime import datetime, time, timedelta

        # Completed activities across categories for the distribution chart.
        for category, minutes in (("Coding", 180), ("Study", 90)):
            database.add_activity(
                Activity(
                    id=None,
                    date=today.isoformat(),
                    activity_type=category,
                    name=f"{category} task",
                    estimated_minutes=60,
                )
            )
        for activity in database.get_activities_for_date(today.isoformat()):
            activity.completed = True
            activity.actual_minutes = (
                180 if activity.activity_type == "Coding" else 90
            )
            database.update_activity(activity)

        # Evening-heavy sessions so the rhythm section has evidence.
        for index in range(9):
            started = datetime.combine(
                today - timedelta(days=index % 4), time(18, 0)
            )
            database.record_focus_session(
                1,
                started.isoformat(timespec="seconds"),
                (started + timedelta(minutes=45)).isoformat(timespec="seconds"),
                45,
                actual_seconds=2700,
            )

        controller.show_analytics()
        window = controller.analytics_window
        data = window.dashboard_data

        # Distribution section populated from real records.
        assert data.distribution.total_minutes == 270
        assert [item.category for item in data.distribution.items] == [
            "Coding",
            "Study",
        ]

        # Rhythm section claims a window only with enough sessions.
        assert data.day_hour.status in ("ready", "learning")
        if data.day_hour.status == "ready":
            assert "strongest focus window" in window.rhythm_label.text()

        # Overview deltas and highlights render without exceptions.
        window.render_dashboard(data)
        assert window.highlight_cards["best_day"].value_label.text() != "—"

    def test_learned_section_empty_state(self, app_controller):
        controller = app_controller
        controller.show_analytics()
        window = controller.analytics_window
        data = window.dashboard_data
        assert data.learned == ()
        # The empty-state card is present in the layout.
        assert window.learned_layout.count() == 1

    def test_all_time_range_switches_cleanly(self, app_controller):
        controller = app_controller
        controller.show_analytics()
        window = controller.analytics_window

        window.select_range("all_time")
        assert window.selected_range == "all_time"
        assert window.dashboard_data.range_definition.label == "All Time"
        assert (
            window.dashboard_data.range_definition.previous_start_date
            is None
        )

        window.select_range("90_days")
        assert window.selected_range == "90_days"
        assert window.dashboard_data.range_definition.label == "3 Months"

    def test_light_theme_renders_insights(self, app_controller):
        from UI.theme.design_system import ThemeManager

        controller = app_controller
        controller.show_analytics()
        window = controller.analytics_window

        ThemeManager.set_theme("light")
        try:
            from PySide6.QtWidgets import QApplication

            application = QApplication.instance()
            application.setStyleSheet(ThemeManager.app_stylesheet())
            window.refresh()
            window.show()
            application.processEvents()
            assert window.dashboard_data is not None
            assert window.range_caption_label.text() != ""
        finally:
            ThemeManager.set_theme("dark")
            QApplication.instance().setStyleSheet(
                ThemeManager.app_stylesheet()
            )
        controller = app_controller
        database = controller.database
        today = date.today().isoformat()

        from Modules.activity import Activity

        # 5 completed activities: statistics exist, but below the
        # recommendation threshold.
        for index in range(5):
            database.add_activity(
                Activity(
                    id=None,
                    date=today,
                    activity_type="Study",
                    name=f"Early task {index}",
                    estimated_minutes=30,
                )
            )
        for activity in database.get_activities_for_date(today):
            activity.completed = True
            activity.actual_minutes = 35
            database.update_activity(activity)

        controller.show_analytics()
        window = controller.analytics_window
        summary = window.dashboard_data.calibration.summary

        assert summary.sample_count == 5
        assert summary.suggested_multiplier is None

        # Standard analytic titles and honest no-recommendation copy.
        assert window.bias_card.title_label.text() == "Estimate Bias"
        assert window.bias_card.value_label.text() == "+17%"
        assert window.typical_error_card.title_label.text() == "Typical Error"
        assert window.confidence_card.value_label.text() == "Early signal"
        assert (
            "no recommendation yet"
            in window.confidence_card.detail_label.text()
        )
        assert (
            "Realistic time suggestions unlock"
            in window.calibration_note_label.text()
        )
