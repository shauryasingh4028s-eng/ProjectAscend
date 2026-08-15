"""Smart Activity Estimates: AddActivityDialog behaviour.

Offscreen Qt tests against temporary databases only. The real user
database is never opened. Evidence is created through the public
Database API (add_activity), never by hand-editing SQL.
"""

import pytest

from Modules.activity import Activity
from Modules.calibration_service import RECOMMENDATION_MIN_OBSERVATIONS


TODAY = "2026-08-15"


def completed_activity(activity_type="Coding", estimated=60, actual=90):
    """A finished activity that forms one valid calibration observation."""
    return Activity(
        id=None,
        date="2026-08-01",
        activity_type=activity_type,
        name="Done work",
        estimated_minutes=estimated,
        completed=True,
        actual_minutes=actual,
    )


def seed_observations(database, count, activity_type="Coding",
                      estimated=60, actual=90):
    for _ in range(count):
        database.add_activity(
            completed_activity(activity_type, estimated, actual)
        )


@pytest.fixture
def dialog_factory(qapp):
    """Create dialogs and destroy them deterministically after each test.

    Qt widgets left alive at interpreter shutdown are destroyed in an
    arbitrary order, which can crash teardown; explicit cleanup keeps the
    suite stable.
    """
    created = []

    def factory(database, activity=None):
        from Dialogs.add_activity_dialog import AddActivityDialog

        dialog = AddActivityDialog(database, TODAY, activity)
        created.append(dialog)
        return dialog

    yield factory

    for dialog in created:
        dialog.close()
        dialog.deleteLater()
    qapp.processEvents()


class TestNoEvidence:
    def test_fresh_database_keeps_dialog_clean(self, dialog_factory, database):
        dialog = dialog_factory(database)
        assert dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion is None

    def test_below_threshold_keeps_dialog_clean(self, dialog_factory, database):
        seed_observations(
            database, RECOMMENDATION_MIN_OBSERVATIONS - 1
        )
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        assert dialog.suggestion_frame.isHidden()

    def test_normal_creation_still_works_without_evidence(
        self, dialog_factory, database
    ):
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Reading")
        dialog.activity_name.setText("NCERT")
        dialog.estimated_time.setValue(45)
        dialog.save_activity()

        saved = database.get_activities_for_date(TODAY)
        assert len(saved) == 1
        assert saved[0].name == "NCERT"
        assert saved[0].estimated_minutes == 45


class TestSuggestionDisplay:
    def test_sufficient_evidence_shows_suggestion(self, dialog_factory, database):
        seed_observations(database, 14)  # Coding x1.5
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        assert not dialog.suggestion_frame.isHidden()
        suggestion = dialog.current_suggestion
        assert suggestion.suggested_minutes == 90
        assert dialog.suggestion_headline.text() == (
            "Ascend suggests ~90 min"
        )
        assert dialog.suggestion_difference.text() == (
            "About 30 min more than your estimate."
        )
        assert dialog.suggestion_evidence.text() == (
            "Based on 14 completed Coding activities."
        )
        assert dialog.keep_button.text() == "Keep 60 min"
        assert dialog.use_button.text() == "Use 90 min"

    def test_copy_contains_no_percentages(self, dialog_factory, database):
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        for widget in (
            dialog.suggestion_headline,
            dialog.suggestion_difference,
            dialog.suggestion_evidence,
            dialog.keep_button,
            dialog.use_button,
        ):
            assert "%" not in widget.text()

    def test_category_switch_recomputes(self, dialog_factory, database):
        # Coding has reliable evidence; Meditation must fall back to the
        # overall multiplier (same data here) but the suggestion should
        # still recompute cleanly on switching.
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        assert dialog.current_suggestion.source == "category"

        dialog.activity_type.setCurrentText("Meditation")
        assert dialog.current_suggestion is not None
        assert dialog.current_suggestion.source == "overall"
        assert dialog.suggestion_evidence.text() == (
            "Based on 14 completed activities."
        )

    def test_out_of_range_suggestion_hidden_not_clamped(
        self, dialog_factory, database
    ):
        seed_observations(database, 14)  # x1.5
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(500)  # -> 750 > 600 max

        assert dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion is None
        # And the spinbox value was never altered.
        assert dialog.estimated_time.value() == 500

    def test_equal_suggestion_suppressed(self, dialog_factory, database):
        seed_observations(database, 14, estimated=60, actual=60)  # x1.0
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        assert dialog.suggestion_frame.isHidden()


class TestUserActions:
    def test_keep_preserves_original_estimate(self, dialog_factory, database):
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        dialog.keep_button.click()

        assert dialog.estimated_time.value() == 60
        assert dialog.suggestion_frame.isHidden()

        dialog.activity_name.setText("My task")
        dialog.save_activity()
        saved = database.get_activities_for_date(TODAY)
        assert saved[0].estimated_minutes == 60

    def test_use_applies_but_does_not_save(self, dialog_factory, database):
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        dialog.use_button.click()

        # The input field changed; nothing was persisted yet.
        assert dialog.estimated_time.value() == 90
        assert database.get_activities_for_date(TODAY) == []

        dialog.activity_name.setText("My task")
        dialog.save_activity()
        saved = database.get_activities_for_date(TODAY)
        assert saved[0].estimated_minutes == 90

    def test_no_recommendation_chaining_after_use(self, dialog_factory, database):
        # 60 -> suggested 90 -> Use 90 must NOT immediately become
        # 90 -> suggested 135.
        seed_observations(database, 14)  # x1.5
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        dialog.use_button.click()

        assert dialog.estimated_time.value() == 90
        assert dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion is None

    def test_manual_edit_after_use_re_anchors(self, dialog_factory, database):
        seed_observations(database, 14)  # x1.5
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        dialog.use_button.click()
        assert dialog.suggestion_frame.isHidden()

        # A subsequent MANUAL edit is a new user estimate and may
        # legitimately produce a fresh suggestion anchored to it.
        dialog.estimated_time.setValue(100)
        assert not dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion.entered_minutes == 100
        assert dialog.current_suggestion.suggested_minutes == 150

    def test_manual_override_always_wins(self, dialog_factory, database):
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        # The user ignores the visible suggestion and types their own
        # number; the saved value is exactly what they typed.
        dialog.estimated_time.setValue(75)
        dialog.activity_name.setText("My task")
        dialog.save_activity()

        saved = database.get_activities_for_date(TODAY)
        assert saved[0].estimated_minutes == 75


class TestEditMode:
    def test_edit_mode_anchors_to_existing_estimate(self, dialog_factory, database):
        seed_observations(database, 14)  # x1.5
        database.add_activity(Activity(
            id=None,
            date=TODAY,
            activity_type="Coding",
            name="Planned work",
            estimated_minutes=40,
        ))
        existing = database.get_activities_for_date(TODAY)[0]

        dialog = dialog_factory(database, existing)

        assert dialog.estimated_time.value() == 40
        assert not dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion.suggested_minutes == 60

    def test_edit_mode_keep_and_save_preserves_value(
        self, dialog_factory, database
    ):
        seed_observations(database, 14)
        database.add_activity(Activity(
            id=None,
            date=TODAY,
            activity_type="Coding",
            name="Planned work",
            estimated_minutes=40,
        ))
        existing = database.get_activities_for_date(TODAY)[0]

        dialog = dialog_factory(database, existing)
        dialog.keep_button.click()
        dialog.save_activity()

        updated = database.get_activities_for_date(TODAY)[0]
        assert updated.estimated_minutes == 40

    def test_edit_mode_use_and_save_applies_value(self, dialog_factory, database):
        seed_observations(database, 14)
        database.add_activity(Activity(
            id=None,
            date=TODAY,
            activity_type="Coding",
            name="Planned work",
            estimated_minutes=40,
        ))
        existing = database.get_activities_for_date(TODAY)[0]

        dialog = dialog_factory(database, existing)
        dialog.use_button.click()
        dialog.save_activity()

        updated = database.get_activities_for_date(TODAY)[0]
        assert updated.estimated_minutes == 60


class TestThemes:
    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_dialog_constructs_in_both_themes(
        self, dialog_factory, database, theme
    ):
        from UI.theme.design_system import ThemeManager

        original = ThemeManager.current_theme
        try:
            ThemeManager.set_theme(theme)
            seed_observations(database, 14)
            dialog = dialog_factory(database)
            dialog.activity_type.setCurrentText("Coding")
            dialog.estimated_time.setValue(60)
            assert not dialog.suggestion_frame.isHidden()
            assert dialog.suggestion_headline.text() == (
                "Ascend suggests ~90 min"
            )
        finally:
            ThemeManager.set_theme(original)
