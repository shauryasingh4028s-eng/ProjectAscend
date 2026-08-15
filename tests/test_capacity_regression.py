"""Planner Capacity Intelligence: application-level regression.

The full shell must still start with capacity wired in, every screen
must still render, and the frozen Smart Activity Estimates behaviour in
the Add Activity dialog must be unaffected.

The user's real database location (%LOCALAPPDATA%) is redirected to a
temporary directory so this test can never touch real user data.
"""

from datetime import date, timedelta

import pytest


@pytest.fixture
def app_controller(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    from Modules.app_controller import AppController

    controller = AppController()
    yield controller
    controller.close_database()


class TestApplicationWiring:
    def test_controller_exposes_one_capacity_service(self, app_controller):
        from Modules.capacity_service import CapacityService

        assert isinstance(app_controller.capacity_service, CapacityService)
        assert (
            app_controller.tomorrow_planner.capacity_service
            is app_controller.capacity_service
        )

    def test_all_major_screens_still_construct_and_switch(
        self, app_controller
    ):
        controller = app_controller
        controller.show_dashboard()
        assert controller.shell.current_page_key() == "dashboard"

        for page_key in (
            "planner", "insights", "history", "progress", "settings"
        ):
            controller.shell.show_page(page_key)
            assert controller.shell.current_page_key() == page_key

        controller.show_dashboard()

    def test_planner_page_refresh_updates_capacity(self, app_controller):
        from Modules.activity import Activity

        controller = app_controller
        planner = controller.tomorrow_planner
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        controller.capacity_service.set_available_minutes(tomorrow, 120)
        controller.database.add_activity(Activity(
            id=None,
            date=tomorrow,
            activity_type="Coding",
            name="Project",
            estimated_minutes=180,
        ))
        controller.shell.show_page("planner")

        assert planner.capacity_plan.state == "over_capacity"
        assert planner.capacity_plan.over_capacity_minutes == 60

    def test_capacity_does_not_affect_dashboard(self, app_controller):
        controller = app_controller
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        controller.capacity_service.set_available_minutes(tomorrow, 120)

        # The dashboard remains a goal-based screen in v1.4 #2.
        assert not hasattr(controller.dashboard, "capacity_plan")
        controller.dashboard.load_today_activities()
        controller.dashboard.update_progress_summary()

    def test_capacity_does_not_affect_xp_or_streaks(self, app_controller):
        controller = app_controller
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        xp_before = controller.xp_manager.get_total_xp()
        streak_before = controller.streak_manager.get_current_streak()

        controller.capacity_service.set_available_minutes(tomorrow, 120)
        controller.tomorrow_planner.load_activities()

        assert controller.xp_manager.get_total_xp() == xp_before
        assert (
            controller.streak_manager.get_current_streak() == streak_before
        )

    def test_daily_goal_untouched_by_capacity(self, app_controller):
        controller = app_controller
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        goal_before = controller.database.get_daily_goal()

        controller.capacity_service.set_available_minutes(tomorrow, 120)
        controller.capacity_service.clear_available_minutes(tomorrow)

        assert controller.database.get_daily_goal() == goal_before


class TestSmartEstimatesStillFrozen:
    def test_dialog_suggestion_behaviour_unaffected(self, app_controller):
        from Dialogs.add_activity_dialog import AddActivityDialog
        from Modules.activity import Activity

        controller = app_controller
        database = controller.database
        for _ in range(5):
            database.add_activity(Activity(
                id=None,
                date="2026-08-01",
                activity_type="Coding",
                name="Project",
                estimated_minutes=60,
                completed=True,
                actual_minutes=70,
            ))

        dialog = AddActivityDialog(database, "2026-08-16")
        try:
            dialog.activity_type.setCurrentText("Coding")
            dialog.activity_name.setText("Project")
            dialog.estimated_time.setValue(60)

            assert dialog.current_suggestion is not None
            assert dialog.current_suggestion.suggested_minutes == 70
            assert not dialog.suggestion_frame.isHidden()
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_capacity_reads_the_same_recommendation(self, app_controller):
        from Modules.activity import Activity

        controller = app_controller
        database = controller.database
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        for _ in range(5):
            database.add_activity(Activity(
                id=None,
                date="2026-08-01",
                activity_type="Coding",
                name="Project",
                estimated_minutes=60,
                completed=True,
                actual_minutes=70,
            ))
        database.add_activity(Activity(
            id=None,
            date=tomorrow,
            activity_type="Coding",
            name="Project",
            estimated_minutes=60,
        ))

        plan = controller.capacity_service.build_plan(tomorrow)

        assert plan.planned_workload_minutes == 60
        assert plan.expected_workload_minutes == 70
        assert plan.learned_task_count == 1
