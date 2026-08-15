"""Planner Capacity Intelligence: the Tomorrow Planner surface.

Offscreen Qt tests against temporary databases only; the real user
database is never opened. Activities are always created through the
public Database API, never by hand-editing SQL.

The central guarantee these tests protect is that capacity is advisory:
looking at it, setting available time and clearing it must leave every
activity row byte-identical.
"""

import pytest

from Modules.activity import Activity


@pytest.fixture
def planner_factory(qapp):
    """Create planners and destroy them deterministically.

    Qt widgets left alive at interpreter shutdown are destroyed in an
    arbitrary order, which can crash teardown; explicit cleanup keeps
    the suite stable.
    """
    created = []

    def factory(database):
        from Dialogs.daily_planner import DailyPlanner

        planner = DailyPlanner(database)
        created.append(planner)
        return planner

    yield factory

    for planner in created:
        planner.close()
        planner.deleteLater()
    qapp.processEvents()


def add_activity(database, planner, name, estimated, activity_type="Homework",
                 completed=False, actual=0):
    database.add_activity(Activity(
        id=None,
        date=planner.selected_date,
        activity_type=activity_type,
        name=name,
        estimated_minutes=estimated,
        completed=completed,
        actual_minutes=actual,
    ))


def activity_rows(database):
    database.cursor.execute("SELECT * FROM activities ORDER BY id")
    return database.cursor.fetchall()


def visible_support_text(planner):
    # isHidden() reflects the explicit shown/hidden state, which is what
    # the card controls. isVisible() would be False for every label
    # simply because the planner itself is never shown in these
    # offscreen tests.
    return " ".join(
        label.text()
        for label in planner.capacity_support_labels
        if not label.isHidden()
    )


class TestFreshPlanner:
    def test_planner_constructs_with_capacity_card(
        self, planner_factory, database
    ):
        planner = planner_factory(database)

        assert planner.capacity_card is not None
        assert planner.capacity_plan is not None

    def test_capacity_card_sits_between_date_and_activities(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        layout = planner.layout()

        widgets = [
            layout.itemAt(index).widget()
            for index in range(layout.count())
        ]
        assert widgets[1] is planner.capacity_card
        assert len(widgets) == 3

    def test_empty_planner_says_nothing_is_planned(
        self, planner_factory, database
    ):
        planner = planner_factory(database)

        assert planner.capacity_headline.text() == "Nothing planned yet."

    def test_empty_planner_does_not_ask_for_work(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        text = (
            planner.capacity_headline.text()
            + visible_support_text(planner)
        ).lower()

        assert "add an activity" not in text


class TestNoCapacityState:
    def test_workload_shown_without_a_verdict(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        add_activity(database, planner, "Science", 45)
        planner.load_activities()

        assert planner.capacity_headline.text() == (
            "About 1h 45m of expected work planned."
        )
        assert (
            "Add the time you have available to see how it fits."
            in visible_support_text(planner)
        )

    def test_set_button_reads_set_when_nothing_is_stored(
        self, planner_factory, database
    ):
        planner = planner_factory(database)

        assert planner.set_available_time_button.text() == "Set"
        assert planner.clear_available_time_button.isHidden()

    def test_input_rests_at_zero_and_is_not_a_suggestion(
        self, planner_factory, database
    ):
        planner = planner_factory(database)

        assert planner.available_time_input.value() == 0
        assert planner.capacity_plan.available_minutes is None

    def test_daily_goal_is_not_used_as_capacity(
        self, planner_factory, database
    ):
        database.set_daily_goal(360)
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()

        assert planner.capacity_plan.available_minutes is None
        assert "6h" not in visible_support_text(planner)


class TestCapacityStates:
    def set_available(self, planner, minutes):
        planner.available_time_input.setValue(minutes)
        planner.set_available_time_button.click()

    def test_under_capacity(self, planner_factory, database):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        add_activity(database, planner, "Science", 80)
        planner.load_activities()
        self.set_available(planner, 240)

        assert planner.capacity_plan.state == "under_capacity"
        assert planner.capacity_headline.text() == (
            "You have about 1h 40m of open capacity."
        )
        assert "Available 4h · Expected ~2h 20m" in (
            visible_support_text(planner)
        )

    def test_near_capacity(self, planner_factory, database):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 170)
        planner.load_activities()
        self.set_available(planner, 180)

        assert planner.capacity_plan.state == "near_capacity"
        assert planner.capacity_headline.text() == (
            "This plan uses almost all of your available time."
        )
        assert "About 10m spare." in visible_support_text(planner)

    def test_over_capacity(self, planner_factory, database):
        planner = planner_factory(database)
        for name, minutes in (
            ("Maths", 60), ("Science", 45), ("Coding", 70),
            ("English", 40), ("Revision", 35),
        ):
            add_activity(database, planner, name, minutes)
        planner.load_activities()
        self.set_available(planner, 180)

        assert planner.capacity_plan.state == "over_capacity"
        assert planner.capacity_headline.text() == (
            "This plan is about 1h 10m beyond your available time."
        )
        assert (
            "3 activities fit within your available time; 2 go beyond."
            in visible_support_text(planner)
        )
        # The ordering rule stays an internal detail of the engine.
        assert "based on the order" not in visible_support_text(planner)

    def test_no_tasks_with_available_time(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        self.set_available(planner, 180)

        assert planner.capacity_plan.state == "no_tasks"
        assert planner.capacity_headline.text() == "Nothing planned yet."
        assert "You have 3h available." in visible_support_text(planner)

    def test_completed_activities_are_reported_separately(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(
            database, planner, "Done", 60, completed=True, actual=65
        )
        add_activity(database, planner, "Pending", 45)
        planner.load_activities()
        self.set_available(planner, 180)

        assert planner.capacity_plan.expected_workload_minutes == 45
        assert "1 activity already complete (1h 5m)." in (
            visible_support_text(planner)
        )

    def test_one_task_over_capacity_shows_no_fit_count(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 120)
        planner.load_activities()
        self.set_available(planner, 60)

        text = visible_support_text(planner)
        assert planner.capacity_plan.state == "over_capacity"
        assert "go beyond" not in text
        assert "goes beyond" not in text
        assert "0 activities" not in text

    def test_windows_acceptance_scenario_is_concise(
        self, planner_factory, database
    ):
        # Available 60, user estimate 60, learned expectation 70.
        planner = planner_factory(database)
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
        add_activity(
            database, planner, "Project", 60, activity_type="Coding"
        )
        planner.load_activities()
        self.set_available(planner, 60)

        shown = [
            label.text()
            for label in planner.capacity_support_labels
            if not label.isHidden()
        ]
        assert planner.capacity_headline.text() == (
            "This plan is about 10m beyond your available time."
        )
        assert shown == [
            "Available 1h · Expected ~1h 10m",
            "Your history suggests ~10m more for this plan.",
        ]

    def test_changing_available_time_hides_stale_provenance(
        self, planner_factory, database
    ):
        """The real acceptance walkthrough, in the live planner.

        estimated 60, expected ~70. The learned sentence explains the
        overload at 60 minutes, then steps aside once the user gives
        themselves enough time - while the expected workload stays 70
        throughout.
        """
        planner = planner_factory(database)
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
        add_activity(
            database, planner, "Project", 60, activity_type="Coding"
        )
        planner.load_activities()

        # Over capacity: the adjustment explains part of the overload.
        self.set_available(planner, 60)
        assert planner.capacity_plan.state == "over_capacity"
        assert planner.capacity_plan.expected_workload_minutes == 70
        assert "Your history suggests" in visible_support_text(planner)

        # Near capacity: the user has just resolved it themselves.
        self.set_available(planner, 70)
        assert planner.capacity_plan.state == "near_capacity"
        assert planner.capacity_plan.expected_workload_minutes == 70
        assert "Your history suggests" not in visible_support_text(planner)

        # Under capacity: still hidden.
        self.set_available(planner, 100)
        assert planner.capacity_plan.state == "under_capacity"
        assert planner.capacity_plan.expected_workload_minutes == 70
        assert "Your history suggests" not in visible_support_text(planner)

        # Clearing returns to the no-capacity state, where the
        # provenance is useful again.
        planner.clear_available_time_button.click()
        assert planner.capacity_plan.state == "no_capacity_data"
        assert planner.capacity_plan.expected_workload_minutes == 70
        assert "Your history suggests" in visible_support_text(planner)

    def test_unused_support_labels_are_hidden(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()
        self.set_available(planner, 240)

        hidden = [
            label for label in planner.capacity_support_labels
            if label.isHidden()
        ]
        # Only the key-numbers line applies in this state.
        assert len(hidden) == 3
        assert all(not label.text() for label in hidden)

    def test_no_learned_adjustment_shows_no_explanation(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()
        self.set_available(planner, 240)

        text = visible_support_text(planner)
        assert "history" not in text
        assert "~0m" not in text

    def test_no_move_action_is_offered(self, planner_factory, database):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 200)
        planner.load_activities()
        self.set_available(planner, 60)

        text = (
            planner.capacity_headline.text()
            + visible_support_text(planner)
        ).lower()
        assert "move" not in text

        from PySide6.QtWidgets import QPushButton

        labels = {
            button.text()
            for button in planner.capacity_card.findChildren(QPushButton)
        }
        assert labels == {"Change", "Clear"}


class TestAvailableTimeInteractions:
    def test_set_available_time_persists(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        planner.available_time_input.setValue(180)
        planner.set_available_time_button.click()

        assert planner.capacity_plan.available_minutes == 180
        assert planner.capacity_service.get_available_minutes(
            planner.selected_date
        ) == 180

    def test_button_becomes_change_once_set(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        planner.available_time_input.setValue(180)
        planner.set_available_time_button.click()

        assert planner.set_available_time_button.text() == "Change"
        assert not planner.clear_available_time_button.isHidden()

    def test_changing_available_time_updates_the_verdict(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 150)
        planner.load_activities()

        planner.available_time_input.setValue(120)
        planner.set_available_time_button.click()
        assert planner.capacity_plan.state == "over_capacity"

        planner.available_time_input.setValue(240)
        planner.set_available_time_button.click()
        assert planner.capacity_plan.state == "under_capacity"

    def test_clear_returns_to_the_invite_state(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()

        planner.available_time_input.setValue(180)
        planner.set_available_time_button.click()
        planner.clear_available_time_button.click()

        assert planner.capacity_plan.available_minutes is None
        assert planner.capacity_plan.state == "no_capacity_data"
        assert planner.set_available_time_button.text() == "Set"
        assert planner.clear_available_time_button.isHidden()

    def test_zero_available_time_is_honoured(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 30)
        planner.load_activities()

        planner.available_time_input.setValue(0)
        planner.set_available_time_button.click()

        assert planner.capacity_plan.available_minutes == 0
        assert planner.capacity_plan.state == "over_capacity"

    def test_stored_value_survives_a_new_planner(
        self, planner_factory, database
    ):
        first = planner_factory(database)
        first.available_time_input.setValue(195)
        first.set_available_time_button.click()

        second = planner_factory(database)

        assert second.capacity_plan.available_minutes == 195
        assert second.available_time_input.value() == 195


class TestActivitiesAreNeverModified:
    def test_rows_identical_across_every_capacity_interaction(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        add_activity(database, planner, "Coding", 70, activity_type="Coding")
        add_activity(
            database, planner, "Done", 30, completed=True, actual=35
        )
        planner.load_activities()

        before = activity_rows(database)

        planner.available_time_input.setValue(60)
        planner.set_available_time_button.click()
        planner.available_time_input.setValue(600)
        planner.set_available_time_button.click()
        planner.available_time_input.setValue(0)
        planner.set_available_time_button.click()
        planner.clear_available_time_button.click()
        planner.load_activities()
        planner.refresh_capacity()

        assert activity_rows(database) == before

    def test_learned_expectation_is_not_written_back(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        # Five completed sessions unlock the exact-activity tier.
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
        add_activity(
            database, planner, "Project", 60, activity_type="Coding"
        )
        planner.load_activities()
        planner.available_time_input.setValue(180)
        planner.set_available_time_button.click()

        assert planner.capacity_plan.expected_workload_minutes == 70

        pending = [
            item for item
            in database.get_activities_for_date(planner.selected_date)
            if not item.completed
        ][0]
        assert pending.estimated_minutes == 60
        assert pending.original_estimate_minutes == 60

    def test_schema_version_unchanged(self, planner_factory, database):
        from Database.database import SCHEMA_VERSION

        planner = planner_factory(database)
        planner.available_time_input.setValue(180)
        planner.set_available_time_button.click()

        database.cursor.execute("PRAGMA user_version")
        assert database.cursor.fetchone()[0] == SCHEMA_VERSION


class TestExistingPlannerBehaviour:
    def test_summary_and_count_unchanged(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        add_activity(database, planner, "Science", 45)
        planner.load_activities()

        assert planner.count_label.text() == "2 activities planned"
        assert planner.summary_label.text() == "1h 45m planned"

    def test_singular_count_unchanged(self, planner_factory, database):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()

        assert planner.count_label.text() == "1 activity planned"

    def test_planned_summary_still_uses_user_estimates(
        self, planner_factory, database
    ):
        # The existing header summary is the user's own arithmetic and
        # must not silently become the learned expectation.
        planner = planner_factory(database)
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
        add_activity(
            database, planner, "Project", 60, activity_type="Coding"
        )
        planner.load_activities()

        assert planner.summary_label.text() == "1h 0m planned"
        assert planner.capacity_plan.expected_workload_minutes == 70

    def test_empty_state_unchanged(self, planner_factory, database):
        planner = planner_factory(database)

        assert planner.empty_label.isVisible() or planner.isHidden()
        assert planner.summary_label.text() == "Nothing planned"

    def test_activity_list_still_populates(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        add_activity(database, planner, "Maths", 60)
        planner.load_activities()

        assert planner.activity_list.count() == 1

    def test_header_actions_unchanged(self, planner_factory, database):
        planner = planner_factory(database)

        assert planner.header_actions() == (planner.add_activity_button,)

    def test_selected_date_is_tomorrow(self, planner_factory, database):
        from datetime import date, timedelta

        planner = planner_factory(database)

        assert planner.selected_date == (
            date.today() + timedelta(days=1)
        ).isoformat()

    def test_add_activity_refreshes_capacity(
        self, planner_factory, database
    ):
        planner = planner_factory(database)
        planner.available_time_input.setValue(120)
        planner.set_available_time_button.click()
        assert planner.capacity_plan.state == "no_tasks"

        add_activity(database, planner, "Maths", 150)
        planner.load_activities()

        assert planner.capacity_plan.state == "over_capacity"
        assert planner.capacity_plan.over_capacity_minutes == 30


class TestThemes:
    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_planner_constructs_in_both_themes(
        self, planner_factory, database, theme
    ):
        from UI.theme.design_system import ThemeManager

        original = ThemeManager.current_theme
        try:
            ThemeManager.set_theme(theme)
            planner = planner_factory(database)
            add_activity(database, planner, "Maths", 200)
            planner.load_activities()
            planner.available_time_input.setValue(120)
            planner.set_available_time_button.click()

            assert planner.capacity_card.objectName() == "LearnedInsight"
            assert planner.capacity_headline.text()
        finally:
            ThemeManager.set_theme(original)

    def test_card_reuses_existing_object_names(
        self, planner_factory, database
    ):
        planner = planner_factory(database)

        assert planner.capacity_card.objectName() == "LearnedInsight"
        assert planner.capacity_headline.objectName() == "CompactStatValue"
        for label in planner.capacity_support_labels:
            assert label.objectName() == "MutedText"
        assert planner.set_available_time_button.objectName() == (
            "GhostButton"
        )
        assert planner.clear_available_time_button.objectName() == (
            "GhostButton"
        )
