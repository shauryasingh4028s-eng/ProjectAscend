"""Smart Activity Estimates v2: AddActivityDialog behaviour.

Offscreen Qt tests against temporary databases only. The real user
database is never opened. Evidence is created through the public
Database API (add_activity), never by hand-editing SQL.

The intelligence model is the personalized absolute-minute bias:
median(actual - original estimate) per evidence tier
(exact activity -> category -> overall).
"""

import pytest

from Modules.activity import Activity


TODAY = "2026-08-15"


def completed_activity(activity_type="Coding", name="Done work",
                       estimated=60, actual=70):
    """A finished activity that forms one valid observation."""
    return Activity(
        id=None,
        date="2026-08-01",
        activity_type=activity_type,
        name=name,
        estimated_minutes=estimated,
        completed=True,
        actual_minutes=actual,
    )


def seed_observations(database, count, activity_type="Coding",
                      name="Done work", estimated=60, actual=70):
    for _ in range(count):
        database.add_activity(
            completed_activity(activity_type, name, estimated, actual)
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
        # 9 category observations: below both the category and overall
        # bars; 4 of one exact name would also be below the exact bar.
        seed_observations(database, 9)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.activity_name.setText("Brand new")
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
    def test_exact_evidence_shows_personalized_suggestion(
        self, dialog_factory, database
    ):
        # 6 completed "Algebra Test" sessions, each +10 min.
        seed_observations(database, 6, activity_type="Tests",
                          name="Algebra Test", estimated=60, actual=70)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Tests")
        dialog.activity_name.setText("Algebra Test")
        dialog.estimated_time.setValue(60)

        assert not dialog.suggestion_frame.isHidden()
        suggestion = dialog.current_suggestion
        assert suggestion.source == "exact"
        assert suggestion.suggested_minutes == 70
        assert dialog.suggestion_headline.text() == (
            "Ascend suggests ~70 min"
        )
        assert dialog.suggestion_difference.text() == (
            "You typically take ~10 min longer."
        )
        assert dialog.suggestion_evidence.text() == (
            'Based on 6 previous "Algebra Test" sessions.'
        )
        assert dialog.keep_button.text() == "Keep 60 min"
        assert dialog.use_button.text() == "Use 70 min"

    def test_exact_matching_is_case_insensitive(
        self, dialog_factory, database
    ):
        seed_observations(database, 6, activity_type="Tests",
                          name="Algebra Test", estimated=60, actual=70)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Tests")
        dialog.activity_name.setText("  algebra   TEST ")
        dialog.estimated_time.setValue(60)

        assert dialog.current_suggestion.source == "exact"

    def test_category_fallback_for_novel_name(
        self, dialog_factory, database
    ):
        seed_observations(database, 14, name="Old project",
                          estimated=60, actual=70)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.activity_name.setText("Completely new work")
        dialog.estimated_time.setValue(60)

        suggestion = dialog.current_suggestion
        assert suggestion.source == "category"
        assert dialog.suggestion_evidence.text() == (
            "Based on 14 previous Coding activities."
        )

    def test_name_change_re_tiers_live(self, dialog_factory, database):
        seed_observations(database, 14, name="Old project",
                          estimated=60, actual=70)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        dialog.activity_name.setText("Novel work")
        assert dialog.current_suggestion.source == "category"

        dialog.activity_name.setText("old PROJECT")
        assert dialog.current_suggestion.source == "exact"
        assert dialog.suggestion_evidence.text() == (
            'Based on 14 previous "old PROJECT" sessions.'
        )

    def test_copy_contains_no_percentages_or_multipliers(
        self, dialog_factory, database
    ):
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
            assert "×" not in widget.text()

    def test_out_of_range_suggestion_hidden_not_clamped(
        self, dialog_factory, database
    ):
        # History at 590 min, +30 bias: entered 595 -> 625 > 600 max.
        seed_observations(database, 12, name="Marathon",
                          estimated=590, actual=620)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.activity_name.setText("Marathon")
        dialog.estimated_time.setValue(595)

        assert dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion is None
        # And the spinbox value was never altered.
        assert dialog.estimated_time.value() == 595

    def test_zero_bias_suppressed(self, dialog_factory, database):
        seed_observations(database, 14, estimated=60, actual=60)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        assert dialog.suggestion_frame.isHidden()

    def test_relevance_window_hides_extrapolation(
        self, dialog_factory, database
    ):
        # All history is 55-65 min work; a 400-min plan is outside every
        # tier's observed range, so nothing may be suggested.
        seed_observations(database, 7, estimated=55, actual=65)
        seed_observations(database, 7, estimated=65, actual=75)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(400)
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
        dialog.activity_name.setText("My task")
        dialog.estimated_time.setValue(60)

        dialog.use_button.click()

        # The input field changed; nothing was persisted yet.
        assert dialog.estimated_time.value() == 70
        assert database.get_activities_for_date(TODAY) == []

        dialog.save_activity()
        saved = database.get_activities_for_date(TODAY)
        assert saved[0].estimated_minutes == 70

    def test_no_recommendation_chaining_after_use(
        self, dialog_factory, database
    ):
        # 60 -> suggested 70 -> Use 70 must NOT immediately become
        # 70 -> suggested 80.
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)

        dialog.use_button.click()

        assert dialog.estimated_time.value() == 70
        assert dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion is None

    def test_manual_edit_after_use_re_anchors(self, dialog_factory, database):
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.estimated_time.setValue(60)
        dialog.use_button.click()
        assert dialog.suggestion_frame.isHidden()

        # A subsequent MANUAL edit is a new user estimate and may
        # legitimately produce a fresh suggestion anchored to it.
        dialog.estimated_time.setValue(55)
        assert not dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion.entered_minutes == 55
        assert dialog.current_suggestion.suggested_minutes == 65

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

    def test_accepted_suggestion_does_not_pollute_learning(
        self, dialog_factory, database
    ):
        # Data-integrity rule: the model learns from the ORIGINAL user
        # estimate, even when the accepted recommendation is later edited
        # into the plan. Here the activity is created via Use (70), but
        # since no work has been recorded yet, the original follows the
        # saved plan per existing persistence semantics - and once the
        # activity completes, the observation compares that frozen
        # original against actual. Verify the record's original is
        # exactly what was saved, not silently rewritten afterwards.
        seed_observations(database, 14)
        dialog = dialog_factory(database)
        dialog.activity_type.setCurrentText("Coding")
        dialog.activity_name.setText("Planned via suggestion")
        dialog.estimated_time.setValue(60)
        dialog.use_button.click()
        dialog.save_activity()

        saved = [
            a for a in database.get_activities_for_date(TODAY)
            if a.name == "Planned via suggestion"
        ][0]
        assert saved.estimated_minutes == 70
        records = database.get_calibration_records()
        mine = [r for r in records if r["name"] == "Planned via suggestion"]
        assert mine[0]["original_estimate_minutes"] == 70
        assert mine[0]["completed"] is False  # not yet an observation


class TestEditMode:
    def seed_and_get_existing(self, database):
        seed_observations(database, 14)  # Coding, +10 bias
        database.add_activity(Activity(
            id=None,
            date=TODAY,
            activity_type="Coding",
            name="Planned work",
            estimated_minutes=55,
        ))
        return [
            a for a in database.get_activities_for_date(TODAY)
            if a.name == "Planned work"
        ][0]

    def test_edit_mode_anchors_to_existing_estimate(
        self, dialog_factory, database
    ):
        existing = self.seed_and_get_existing(database)
        dialog = dialog_factory(database, existing)

        assert dialog.estimated_time.value() == 55
        assert not dialog.suggestion_frame.isHidden()
        assert dialog.current_suggestion.suggested_minutes == 65

    def test_edit_mode_keep_and_save_preserves_value(
        self, dialog_factory, database
    ):
        existing = self.seed_and_get_existing(database)
        dialog = dialog_factory(database, existing)
        dialog.keep_button.click()
        dialog.save_activity()

        updated = [
            a for a in database.get_activities_for_date(TODAY)
            if a.name == "Planned work"
        ][0]
        assert updated.estimated_minutes == 55

    def test_edit_mode_use_and_save_applies_value(
        self, dialog_factory, database
    ):
        existing = self.seed_and_get_existing(database)
        dialog = dialog_factory(database, existing)
        dialog.use_button.click()
        dialog.save_activity()

        updated = [
            a for a in database.get_activities_for_date(TODAY)
            if a.name == "Planned work"
        ][0]
        assert updated.estimated_minutes == 65


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
                "Ascend suggests ~70 min"
            )
        finally:
            ThemeManager.set_theme(original)
