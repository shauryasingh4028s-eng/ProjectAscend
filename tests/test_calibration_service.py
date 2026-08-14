"""Calibration statistics: formulas, evidence levels and recommendations.

These tests exercise the pure statistics layer with hand-built records, so
they do not depend on any database at all.
"""

import pytest

from Modules.calibration_service import (
    MIN_OBSERVATIONS_FOR_STATS,
    RECOMMENDATION_MIN_OBSERVATIONS,
    build_calibration_report,
    describe_bias,
    evidence_label,
    evidence_level_for,
    format_error_percent,
    format_plain_percent,
    make_observations,
    recommended_estimate,
)


def record(
    activity_id,
    activity_type="Coding",
    name="Task",
    estimated=100,
    actual=100,
    completed=True,
    original=None,
):
    return {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "name": name,
        "estimated_minutes": estimated,
        "original_estimate_minutes": (
            estimated if original is None else original
        ),
        "completed": completed,
        "actual_minutes": actual,
    }


class TestBasicCalculation:
    def test_perfect_estimate_has_zero_error(self):
        report = build_calibration_report([record(1, estimated=100, actual=100)])
        summary = report.summary
        assert summary.sample_count == 1
        assert summary.mean_relative_error == 0.0
        assert summary.mean_absolute_percentage_error == 0.0
        assert summary.bias == "balanced"
        assert report.observations[0].absolute_error_minutes == 0

    def test_underestimate_is_positive_error(self):
        # estimate 100, actual 125 -> error +25% (took longer than planned)
        report = build_calibration_report([record(1, estimated=100, actual=125)])
        summary = report.summary
        assert summary.mean_relative_error == pytest.approx(0.25)
        assert summary.bias == "underestimate"

    def test_overestimate_is_negative_error(self):
        # estimate 100, actual 75 -> error -25% (finished sooner)
        report = build_calibration_report([record(1, estimated=100, actual=75)])
        summary = report.summary
        assert summary.mean_relative_error == pytest.approx(-0.25)
        assert summary.bias == "overestimate"

    def test_absolute_error_minutes(self):
        observation = make_observations([record(1, estimated=120, actual=150)])[0]
        assert observation.absolute_error_minutes == 30

    def test_absolute_percentage_error_ignores_direction(self):
        observations = make_observations(
            [
                record(1, estimated=100, actual=125),
                record(2, estimated=100, actual=75),
            ]
        )
        assert [o.absolute_percentage_error for o in observations] == [
            pytest.approx(0.25),
            pytest.approx(0.25),
        ]


class TestInvalidData:
    def test_zero_estimate_does_not_crash_and_is_excluded(self):
        report = build_calibration_report([record(1, estimated=0, actual=50)])
        assert report.summary.sample_count == 0
        assert report.summary.excluded_count == 1
        assert report.summary.mean_relative_error is None

    def test_missing_actual_is_not_an_observation(self):
        report = build_calibration_report(
            [record(1, estimated=30, actual=0)]
        )
        assert report.summary.sample_count == 0
        assert report.summary.excluded_count == 1

    def test_incomplete_activity_is_pending_not_observed(self):
        report = build_calibration_report(
            [record(1, estimated=30, actual=40, completed=False)]
        )
        assert report.summary.sample_count == 0
        assert report.summary.pending_count == 1
        assert report.summary.excluded_count == 0

    def test_negative_durations_are_ignored(self):
        report = build_calibration_report(
            [
                record(1, estimated=30, actual=-10),
                record(2, estimated=-5, actual=30),
                record(3, estimated=30, actual=45),
            ]
        )
        assert report.summary.sample_count == 1
        assert report.summary.excluded_count == 2

    def test_mixed_invalid_and_valid_records(self):
        report = build_calibration_report(
            [
                record(1, estimated=0, actual=50),      # excluded
                record(2, estimated=30, actual=40, completed=False),  # pending
                record(3, estimated=30, actual=0),      # excluded
                record(4, estimated=60, actual=90),     # valid
            ]
        )
        summary = report.summary
        assert summary.sample_count == 1
        assert summary.excluded_count == 2
        assert summary.pending_count == 1
        assert summary.mean_relative_error == pytest.approx(0.5)


class TestAggregation:
    def test_multiple_activities_average_correctly(self):
        # +25% and -25% average to 0% (balanced) with a 25% typical error.
        report = build_calibration_report(
            [
                record(1, estimated=100, actual=125),
                record(2, estimated=100, actual=75),
            ]
        )
        summary = report.summary
        assert summary.sample_count == 2
        assert summary.mean_relative_error == pytest.approx(0.0)
        assert summary.mean_absolute_percentage_error == pytest.approx(0.25)
        assert summary.bias == "balanced"

    def test_mean_and_median_are_reported(self):
        # A single extreme outlier moves the mean but not the median.
        report = build_calibration_report(
            [
                record(1, estimated=100, actual=110),
                record(2, estimated=100, actual=120),
                record(3, estimated=100, actual=500),
            ]
        )
        summary = report.summary
        assert summary.mean_relative_error == pytest.approx(1.4333, abs=1e-3)
        assert summary.median_relative_error == pytest.approx(0.2)

    def test_category_statistics_are_isolated(self):
        report = build_calibration_report(
            [
                record(1, activity_type="Coding", estimated=100, actual=120),
                record(2, activity_type="Coding", estimated=100, actual=140),
                record(3, activity_type="Study", estimated=100, actual=90),
                record(4, activity_type="Study", estimated=100, actual=70),
            ]
        )
        categories = {c.activity_type: c for c in report.categories}
        assert set(categories) == {"Coding", "Study"}
        assert categories["Coding"].sample_count == 2
        assert categories["Coding"].mean_relative_error == pytest.approx(0.3)
        assert categories["Study"].sample_count == 2
        assert categories["Study"].mean_relative_error == pytest.approx(-0.2)

    def test_categories_sort_by_sample_count_then_name(self):
        report = build_calibration_report(
            [
                record(1, activity_type="Coding"),
                record(2, activity_type="Study"),
                record(3, activity_type="Study"),
            ]
        )
        names = [c.activity_type for c in report.categories]
        assert names == ["Study", "Coding"]


class TestEvidenceLevels:
    def test_thresholds_are_explicit(self):
        assert evidence_level_for(0) == "insufficient_data"
        assert evidence_level_for(2) == "insufficient_data"
        assert evidence_level_for(MIN_OBSERVATIONS_FOR_STATS) == "early_signal"
        assert evidence_level_for(RECOMMENDATION_MIN_OBSERVATIONS - 1) == "early_signal"
        assert evidence_level_for(RECOMMENDATION_MIN_OBSERVATIONS) == "moderate_confidence"
        assert evidence_level_for(24) == "moderate_confidence"
        assert evidence_level_for(25) == "high_confidence"
        assert evidence_level_for(100) == "high_confidence"

    def test_insufficient_data_never_recommends(self):
        report = build_calibration_report(
            [record(i) for i in range(1, MIN_OBSERVATIONS_FOR_STATS)]
        )
        summary = report.summary
        assert summary.evidence_level == "insufficient_data"
        assert summary.suggested_multiplier is None

    def test_early_signal_reports_stats_but_no_recommendation(self):
        report = build_calibration_report(
            [record(i) for i in range(1, RECOMMENDATION_MIN_OBSERVATIONS)]
        )
        summary = report.summary
        assert summary.evidence_level == "early_signal"
        assert summary.mean_relative_error is not None
        assert summary.suggested_multiplier is None

    def test_sufficient_data_produces_recommendation(self):
        # 12 observations, all taking 18% longer than planned.
        records = [
            record(i, estimated=100, actual=118)
            for i in range(1, RECOMMENDATION_MIN_OBSERVATIONS + 2)
        ]
        report = build_calibration_report(records)
        summary = report.summary
        assert summary.evidence_level == "moderate_confidence"
        assert summary.suggested_multiplier == pytest.approx(1.18, abs=0.01)
        assert summary.bias == "underestimate"

    def test_category_recommendation_requires_category_evidence(self):
        records = [
            record(i, activity_type="Coding", estimated=100, actual=120)
            for i in range(1, RECOMMENDATION_MIN_OBSERVATIONS + 2)
        ]
        records.append(
            record(99, activity_type="Study", estimated=100, actual=200)
        )
        report = build_calibration_report(records)
        categories = {c.activity_type: c for c in report.categories}
        assert categories["Coding"].suggested_multiplier == pytest.approx(1.2)
        assert categories["Study"].suggested_multiplier is None
        assert categories["Study"].evidence_level == "insufficient_data"

    def test_recommended_estimate_rounds_to_five_minutes(self):
        assert recommended_estimate(120, 1.18) == 140
        assert recommended_estimate(60, 1.07) == 65
        assert recommended_estimate(5, 1.0) == 5

    def test_recommended_estimate_refuses_without_multiplier(self):
        assert recommended_estimate(120, None) is None
        assert recommended_estimate(None, 1.2) is None
        assert recommended_estimate(0, 1.2) is None


class TestPresentation:
    def test_format_error_percent(self):
        assert format_error_percent(0.25) == "+25%"
        assert format_error_percent(-0.25) == "-25%"
        assert format_error_percent(0.0) == "0%"
        assert format_error_percent(0.183) == "+18%"

    def test_format_plain_percent(self):
        assert format_plain_percent(0.3469) == "35%"
        assert format_plain_percent(0.0) == "0%"
        assert format_plain_percent(1.0) == "100%"

    def test_evidence_and_bias_labels(self):
        assert evidence_label("moderate_confidence") == "Moderate confidence"
        assert describe_bias(0.1) == "underestimate"
        assert describe_bias(-0.1) == "overestimate"
        assert describe_bias(0.01) == "balanced"
        assert describe_bias(None) == "unknown"

    def test_original_estimate_preferred_over_edited_estimate(self):
        # The plan said 60; the estimate was later edited to 90. Calibration
        # must compare 60 against the actual result.
        report = build_calibration_report(
            [record(1, estimated=90, original=60, actual=65)]
        )
        observation = report.observations[0]
        assert observation.estimated_minutes == 60
        assert observation.relative_error == pytest.approx(0.0833, abs=1e-3)

    def test_report_generated_at_is_iso_date(self):
        report = build_calibration_report([record(1)], generated_at="2026-08-14")
        assert report.generated_at == "2026-08-14"
