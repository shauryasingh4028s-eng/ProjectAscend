"""Smart Activity Estimates: pure suggestion-selection logic.

These tests exercise the Qt-free helper with hand-built calibration
records, exactly like the calibration service tests. No database and no
GUI are involved.
"""

import pytest

from Modules.calibration_service import (
    RECOMMENDATION_MIN_OBSERVATIONS,
    build_calibration_report,
    recommended_estimate,
)
from Modules.estimate_suggestion import (
    build_difference_text,
    build_evidence_text,
    select_evidence,
    suggest_estimate,
)


SPINBOX_MIN = 5
SPINBOX_MAX = 600


def record(
    activity_id,
    activity_type="Coding",
    name="Task",
    estimated=60,
    actual=72,
    completed=True,
):
    return {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "name": name,
        "estimated_minutes": estimated,
        "original_estimate_minutes": estimated,
        "completed": completed,
        "actual_minutes": actual,
    }


def report_with(count, activity_type="Coding", estimated=60, actual=72):
    """A report with `count` identical completed observations."""
    return build_calibration_report([
        record(i, activity_type=activity_type,
               estimated=estimated, actual=actual)
        for i in range(1, count + 1)
    ])


def suggest(report, activity_type="Coding", entered=60):
    return suggest_estimate(
        report, activity_type, entered, SPINBOX_MIN, SPINBOX_MAX
    )


class TestEvidenceThreshold:
    def test_no_records_no_suggestion(self):
        report = build_calibration_report([])
        assert suggest(report) is None

    def test_no_report_no_suggestion(self):
        assert suggest(None) is None

    def test_below_threshold_no_suggestion(self):
        # 9 observations: one below the service's own recommendation
        # threshold. The engine publishes no multiplier, so no suggestion.
        report = report_with(RECOMMENDATION_MIN_OBSERVATIONS - 1)
        assert report.summary.suggested_multiplier is None
        assert suggest(report) is None

    def test_at_threshold_suggestion_available(self):
        # Exactly 10 observations: the engine publishes a multiplier and
        # the suggestion appears. The threshold itself belongs to the
        # calibration service; this test only proves it is respected.
        report = report_with(RECOMMENDATION_MIN_OBSERVATIONS)
        assert report.summary.suggested_multiplier is not None
        suggestion = suggest(report)
        assert suggestion is not None
        assert suggestion.suggested_minutes == 70  # 60 * 1.2 -> 72 -> 70

    def test_incomplete_records_are_not_evidence(self):
        report = build_calibration_report([
            record(i, completed=False)
            for i in range(1, RECOMMENDATION_MIN_OBSERVATIONS + 5)
        ])
        assert suggest(report) is None


class TestEvidenceSelection:
    def test_category_evidence_preferred_over_overall(self):
        # Coding runs long (x1.5); Reading runs on time. Both categories
        # are individually reliable. A Coding suggestion must use the
        # Coding multiplier, not the blended overall one.
        records = [
            record(i, activity_type="Coding", estimated=60, actual=90)
            for i in range(1, 13)
        ] + [
            record(100 + i, activity_type="Reading",
                   estimated=60, actual=60)
            for i in range(1, 13)
        ]
        report = build_calibration_report(records)

        evidence = select_evidence(report, "Coding")
        multiplier, sample_count, source, activity_type = evidence
        assert source == "category"
        assert activity_type == "Coding"
        assert sample_count == 12
        assert multiplier == pytest.approx(1.5)

        suggestion = suggest(report, "Coding", entered=60)
        assert suggestion.suggested_minutes == 90
        assert suggestion.source == "category"

    def test_overall_fallback_when_category_thin(self):
        # Plenty of overall evidence, but the selected category has too
        # few observations of its own: fall back to the overall
        # multiplier, honestly labelled.
        records = [
            record(i, activity_type="Coding", estimated=60, actual=72)
            for i in range(1, 15)
        ] + [
            record(100, activity_type="Reading", estimated=60, actual=120)
        ]
        report = build_calibration_report(records)

        evidence = select_evidence(report, "Reading")
        multiplier, sample_count, source, activity_type = evidence
        assert source == "overall"
        assert activity_type is None
        assert sample_count == report.summary.sample_count
        assert multiplier == report.summary.suggested_multiplier

    def test_unknown_category_uses_overall(self):
        report = report_with(12, activity_type="Coding")
        evidence = select_evidence(report, "Meditation")
        assert evidence is not None
        assert evidence[2] == "overall"

    def test_no_multiplier_anywhere_returns_none(self):
        report = report_with(RECOMMENDATION_MIN_OBSERVATIONS - 1)
        assert select_evidence(report, "Coding") is None


class TestRecommendationValue:
    def test_matches_recommended_estimate_exactly(self):
        # The suggestion must be the untouched output of the existing
        # calibration helper - no reimplemented arithmetic.
        report = report_with(12, estimated=50, actual=61)
        multiplier = report.summary.suggested_multiplier
        for entered in (25, 40, 60, 95, 240):
            suggestion = suggest(report, entered=entered)
            expected = recommended_estimate(entered, multiplier)
            if expected == entered or not (
                SPINBOX_MIN <= expected <= SPINBOX_MAX
            ):
                assert suggestion is None
            else:
                assert suggestion.suggested_minutes == expected

    def test_difference_is_relative_to_entered_value(self):
        report = report_with(12)  # x1.2
        suggestion = suggest(report, entered=100)  # -> 120
        assert suggestion.suggested_minutes == 120
        assert suggestion.difference_minutes == 20
        assert suggestion.entered_minutes == 100


class TestSuppression:
    def test_equal_recommendation_suppressed(self):
        # Perfectly calibrated user: multiplier 1.0 reproduces the entered
        # value, which is noise, not intelligence.
        report = report_with(12, estimated=60, actual=60)
        assert report.summary.suggested_multiplier == pytest.approx(1.0)
        assert suggest(report, entered=60) is None

    def test_rounding_identity_suppressed(self):
        # A small multiplier that rounds back to the entered value after
        # the 5-minute step must also be suppressed.
        report = report_with(12, estimated=100, actual=101)  # x1.01
        assert suggest(report, entered=100) is None


class TestRangeHonesty:
    def test_out_of_range_recommendation_hidden_not_clamped(self):
        # 500 min * x1.5 = 750 min: beyond the dialog's 600-min maximum.
        # The suggestion is hidden entirely; the engine's number is never
        # misrepresented by clamping it to 600.
        report = report_with(12, estimated=60, actual=90)  # x1.5
        assert suggest(report, entered=500) is None

    def test_in_range_recommendation_still_shown(self):
        report = report_with(12, estimated=60, actual=90)  # x1.5
        suggestion = suggest(report, entered=400)  # -> 600, right at max
        assert suggestion is not None
        assert suggestion.suggested_minutes == 600

    def test_below_minimum_recommendation_hidden(self):
        # A strong overestimator: 10 min * x0.4 -> 5 min is at the
        # minimum and fine, but a custom higher minimum hides it.
        report = report_with(12, estimated=100, actual=40)  # x0.4
        assert suggest_estimate(report, "Coding", 10, 15, 600) is None


class TestCopy:
    def test_headline_is_time_first(self):
        report = report_with(14)
        suggestion = suggest(report, entered=60)
        assert suggestion.headline == "Ascend suggests ~70 min"
        assert "%" not in suggestion.headline

    def test_no_percentages_anywhere_in_actionable_copy(self):
        report = report_with(14)
        suggestion = suggest(report, entered=60)
        for text in (
            suggestion.headline,
            suggestion.difference_text,
            suggestion.evidence_text,
            suggestion.keep_label,
            suggestion.use_label,
        ):
            assert "%" not in text

    def test_difference_more(self):
        assert build_difference_text(8) == (
            "About 8 min more than your estimate."
        )

    def test_difference_less(self):
        assert build_difference_text(-10) == (
            "About 10 min less than your estimate."
        )

    def test_category_evidence_copy(self):
        assert build_evidence_text(14, "category", "Coding") == (
            "Based on 14 completed Coding activities."
        )

    def test_overall_evidence_copy(self):
        assert build_evidence_text(23, "overall", None) == (
            "Based on 23 completed activities."
        )

    def test_action_labels_are_concrete(self):
        report = report_with(14)
        suggestion = suggest(report, entered=60)
        assert suggestion.keep_label == "Keep 60 min"
        assert suggestion.use_label == "Use 70 min"
