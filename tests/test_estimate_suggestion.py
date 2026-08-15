"""Smart Activity Estimates v2: pure suggestion-selection logic.

These tests exercise the Qt-free intelligence layer with hand-built
records, exactly like the calibration service tests. No database and no
GUI are involved.

The layer learns an absolute-minute bias, median(actual - original
estimate), per evidence tier (exact activity -> category -> overall),
with strict name identity, a relevance window, and honest hiding rules.
"""

from statistics import median

import pytest

from Modules.calibration_service import RECOMMENDATION_MIN_OBSERVATIONS
from Modules.estimate_suggestion import (
    CATEGORY_MIN_OBSERVATIONS,
    EXACT_MIN_OBSERVATIONS,
    OVERALL_MIN_OBSERVATIONS,
    build_difference_text,
    build_evidence_text,
    normalize_name,
    round_to_step,
    suggest_estimate,
)


SPINBOX_MIN = 5
SPINBOX_MAX = 600

_next_id = [0]


def record(
    activity_type="Coding",
    name="Project",
    estimated=60,
    actual=70,
    completed=True,
):
    _next_id[0] += 1
    return {
        "activity_id": _next_id[0],
        "activity_type": activity_type,
        "name": name,
        "estimated_minutes": estimated,
        "original_estimate_minutes": estimated,
        "completed": completed,
        "actual_minutes": actual,
    }


def records_with(count, **kwargs):
    return [record(**kwargs) for _ in range(count)]


def suggest(records, activity_type="Coding", name="Project", entered=60,
            minimum=SPINBOX_MIN, maximum=SPINBOX_MAX):
    return suggest_estimate(
        records, activity_type, name, entered, minimum, maximum
    )


class TestNormalization:
    def test_trims_and_collapses_whitespace(self):
        assert normalize_name("  Maths   Test ") == "maths test"

    def test_case_insensitive(self):
        assert normalize_name("Maths Test") == normalize_name("maths test")
        assert normalize_name("MATHS TEST") == normalize_name("Maths test")

    def test_different_strings_stay_different(self):
        base = normalize_name("Maths Test")
        assert normalize_name("Maths Test 2") != base
        assert normalize_name("Maths Test - Chapter 5") != base
        assert normalize_name("Maths Test (Final)") != base

    def test_blank_names_normalize_empty(self):
        assert normalize_name("") == ""
        assert normalize_name("   ") == ""
        assert normalize_name(None) == ""


class TestExactTier:
    def test_below_exact_threshold_falls_back(self):
        # 4 exact repeats: one below the exact threshold. Category has
        # enough total evidence, so the category tier is used instead.
        records = (
            records_with(EXACT_MIN_OBSERVATIONS - 1,
                         name="Algebra Test", estimated=60, actual=90)
            + records_with(10, name="Other work",
                           estimated=60, actual=70)
        )
        suggestion = suggest(records, name="Algebra Test")
        assert suggestion.source == "category"

    def test_at_exact_threshold_exact_wins(self):
        records = (
            records_with(EXACT_MIN_OBSERVATIONS,
                         name="Algebra Test", estimated=60, actual=90)
            + records_with(10, name="Other work",
                           estimated=60, actual=70)
        )
        suggestion = suggest(records, name="Algebra Test")
        assert suggestion.source == "exact"
        assert suggestion.sample_count == EXACT_MIN_OBSERVATIONS
        assert suggestion.suggested_minutes == 90  # bias +30
        assert suggestion.activity_name == "Algebra Test"

    def test_case_and_whitespace_variants_merge(self):
        records = [
            record(name="Maths Test", estimated=60, actual=75),
            record(name="maths test", estimated=60, actual=75),
            record(name="MATHS TEST", estimated=60, actual=75),
            record(name="  Maths   Test ", estimated=60, actual=75),
            record(name="Maths test", estimated=60, actual=75),
        ]
        suggestion = suggest(records, name="Maths Test")
        assert suggestion is not None
        assert suggestion.source == "exact"
        assert suggestion.sample_count == 5

    @pytest.mark.parametrize("other_name", [
        "Maths Test 2",
        "Maths Test - Chapter 5",
        "Maths Test (Final)",
    ])
    def test_similar_names_do_not_merge(self, other_name):
        # 3 genuine repeats + 2 similar-but-different names: the exact
        # tier must not reach its threshold of 5.
        records = (
            records_with(3, name="Maths Test", estimated=60, actual=90)
            + records_with(2, name=other_name, estimated=60, actual=90)
        )
        suggestion = suggest(records, name="Maths Test")
        assert suggestion is None  # no tier is reliable

    def test_same_name_different_category_not_exact(self):
        # "Practice" under Music Practice is not the same activity as
        # "Practice" under Coding.
        records = records_with(
            6, activity_type="Music Practice",
            name="Practice", estimated=60, actual=90,
        )
        suggestion = suggest(records, activity_type="Coding",
                             name="Practice")
        assert suggestion is None

    def test_blank_name_never_forms_exact_group(self):
        records = records_with(6, name="", estimated=60, actual=90)
        suggestion = suggest(records, name="")
        # Six records is still below the category threshold of 10, and
        # the blank name must not have unlocked the exact tier.
        assert suggestion is None


class TestCategoryTier:
    def test_below_category_threshold_falls_to_overall(self):
        # 9 Coding + 6 Reading: Coding alone is below 10, but overall
        # (15) is reliable.
        records = (
            records_with(CATEGORY_MIN_OBSERVATIONS - 1,
                         activity_type="Coding", name="A",
                         estimated=60, actual=70)
            + records_with(6, activity_type="Reading", name="B",
                           estimated=60, actual=70)
        )
        suggestion = suggest(records, activity_type="Coding", name="New")
        assert suggestion.source == "overall"

    def test_at_category_threshold_category_wins(self):
        records = (
            records_with(CATEGORY_MIN_OBSERVATIONS,
                         activity_type="Coding", name="A",
                         estimated=60, actual=70)
            + records_with(6, activity_type="Reading", name="B",
                           estimated=60, actual=100)
        )
        suggestion = suggest(records, activity_type="Coding", name="New")
        assert suggestion.source == "category"
        assert suggestion.sample_count == CATEGORY_MIN_OBSERVATIONS
        assert suggestion.suggested_minutes == 70  # Coding bias +10 only


class TestOverallTier:
    def test_below_overall_threshold_no_suggestion(self):
        records = records_with(OVERALL_MIN_OBSERVATIONS - 1,
                               activity_type="Reading", name="B",
                               estimated=60, actual=70)
        assert suggest(records, activity_type="Coding",
                       name="New") is None

    def test_at_overall_threshold_overall_used(self):
        records = records_with(OVERALL_MIN_OBSERVATIONS,
                               activity_type="Reading", name="B",
                               estimated=60, actual=70)
        suggestion = suggest(records, activity_type="Coding", name="New")
        assert suggestion.source == "overall"
        assert suggestion.sample_count == OVERALL_MIN_OBSERVATIONS

    def test_no_records_no_suggestion(self):
        assert suggest([]) is None
        assert suggest(None) is None

    def test_incomplete_records_are_not_evidence(self):
        records = records_with(20, completed=False)
        assert suggest(records) is None


class TestHierarchy:
    def test_exact_beats_category_beats_overall(self):
        # All three tiers reliable but disagreeing: exact +30,
        # category (without exact rows it would be +10), overall mixes
        # in Reading's -20. Exact must win.
        records = (
            records_with(5, activity_type="Coding", name="Deep Work",
                         estimated=60, actual=90)      # exact: +30
            + records_with(10, activity_type="Coding", name="Other",
                           estimated=60, actual=70)    # category filler
            + records_with(10, activity_type="Reading", name="B",
                           estimated=60, actual=40)    # overall noise
        )
        suggestion = suggest(records, activity_type="Coding",
                             name="Deep Work")
        assert suggestion.source == "exact"
        assert suggestion.suggested_minutes == 90

        # A novel name in the same category falls to the category tier.
        suggestion = suggest(records, activity_type="Coding",
                             name="Brand New Task")
        assert suggestion.source == "category"

        # A novel category falls to the overall tier.
        suggestion = suggest(records, activity_type="Exercise",
                             name="Run")
        assert suggestion.source == "overall"

    def test_thresholds_used_by_this_layer_stay_aligned(self):
        # Category/overall bars are single-sourced from the calibration
        # engine's recommendation threshold.
        assert CATEGORY_MIN_OBSERVATIONS == RECOMMENDATION_MIN_OBSERVATIONS
        assert OVERALL_MIN_OBSERVATIONS == RECOMMENDATION_MIN_OBSERVATIONS
        assert EXACT_MIN_OBSERVATIONS == 5


class TestBiasStatistic:
    def test_positive_median_bias(self):
        # Differences: +10, +10, +9, +10, +12 -> median +10.
        actuals = [60, 80, 69, 55, 102]
        estimates = [50, 70, 60, 45, 90]
        records = [
            record(name="Task", estimated=e, actual=a)
            for e, a in zip(estimates, actuals)
        ]
        suggestion = suggest(records, name="Task", entered=60)
        assert suggestion.median_bias_minutes == 10
        assert suggestion.suggested_minutes == 70

    def test_negative_median_bias(self):
        records = records_with(5, name="Revision",
                               estimated=60, actual=55)  # -5 each
        suggestion = suggest(records, name="Revision", entered=60)
        assert suggestion.median_bias_minutes == -5
        assert suggestion.suggested_minutes == 55
        assert suggestion.difference_minutes == -5

    def test_zero_bias_suppressed(self):
        records = records_with(6, name="Task", estimated=60, actual=60)
        assert suggest(records, name="Task", entered=60) is None

    def test_outlier_does_not_move_median(self):
        # Four sessions at +10 and one catastrophic +180: the median
        # stays +10. A mean would have suggested ~104.
        records = (
            records_with(4, name="Task", estimated=60, actual=70)
            + [record(name="Task", estimated=60, actual=240)]
        )
        suggestion = suggest(records, name="Task", entered=60)
        assert suggestion.median_bias_minutes == 10
        assert suggestion.suggested_minutes == 70

    def test_learns_from_original_estimate_not_edited_one(self):
        # The plan was 60 (original) but the record's editable estimate
        # was later changed to 70. The observation layer compares the
        # ORIGINAL against actual, so the learned bias is +15, not +5.
        records = []
        for _ in range(5):
            r = record(name="Task", estimated=60, actual=75)
            r["estimated_minutes"] = 70  # post-hoc edit
            records.append(r)
        suggestion = suggest(records, name="Task", entered=60)
        assert suggestion.median_bias_minutes == 15
        assert suggestion.suggested_minutes == 75

    def test_median_matches_statistics_median(self):
        # Independent check against the standard library, even sample.
        diffs = [4, 7, 11, 16]
        records = [
            record(name="Task", estimated=60, actual=60 + d)
            for d in diffs
        ] + [record(name="Task", estimated=60, actual=60 + 9)]
        suggestion = suggest(records, name="Task", entered=60)
        assert suggestion.median_bias_minutes == median(diffs + [9])


class TestRounding:
    def test_rounds_to_five_minute_step(self):
        assert round_to_step(68) == 70
        assert round_to_step(67) == 65
        assert round_to_step(72.5) == 70 or round_to_step(72.5) == 75
        assert round_to_step(70) == 70

    def test_bias_of_nine_displays_as_ten(self):
        # Entered 60, bias +9 -> raw 69 -> rounded 70. The displayed
        # delta must be 10 (from the rounded value), not 9.
        records = records_with(5, name="Task", estimated=60, actual=69)
        suggestion = suggest(records, name="Task", entered=60)
        assert suggestion.median_bias_minutes == 9
        assert suggestion.suggested_minutes == 70
        assert suggestion.difference_minutes == 10
        assert suggestion.difference_text == (
            "You typically take ~10 min longer."
        )

    def test_small_bias_rounding_to_identity_suppressed(self):
        # Bias +2 on entered 60 -> raw 62 -> rounds back to 60: noise.
        records = records_with(5, name="Task", estimated=60, actual=62)
        assert suggest(records, name="Task", entered=60) is None


class TestRelevanceWindow:
    def test_boundaries_inclusive(self):
        # Observed originals span 30-60; window is 25-65 inclusive.
        records = [
            record(name="Task", estimated=e, actual=e + 10)
            for e in (30, 40, 45, 50, 60)
        ]
        for entered in (25, 30, 45, 60, 65):
            suggestion = suggest(records, name="Task", entered=entered)
            assert suggestion is not None, entered
            assert suggestion.source == "exact"

        for entered in (20, 70, 300):
            assert suggest(records, name="Task", entered=entered) is None

    def test_irrelevant_exact_tier_falls_to_category(self):
        # Exact evidence lives at 30-60 min; the user plans 200 min.
        # The exact tier must not extrapolate; category evidence that
        # covers 200 min takes over.
        records = (
            [record(name="Task", estimated=e, actual=e + 10)
             for e in (30, 40, 45, 50, 60)]
            + [record(name="Long work", estimated=e, actual=e + 30)
               for e in (100, 150, 180, 200, 220, 240, 120, 160, 210, 190)]
        )
        suggestion = suggest(records, name="Task", entered=200)
        assert suggestion.source == "category"

    def test_no_relevant_tier_means_no_suggestion(self):
        records = [
            record(name="Task", estimated=e, actual=e + 10)
            for e in (30, 40, 45, 50, 60, 35, 55, 42, 48, 52)
        ]
        # 300 is outside every tier's window (all originals are 30-60).
        assert suggest(records, name="Task", entered=300) is None


class TestRangeHonesty:
    def test_above_maximum_hidden_not_clamped(self):
        # Entered 595 with bias +30 -> 625 > 600: hidden entirely.
        records = records_with(
            5, name="Marathon", estimated=590, actual=620
        )
        assert suggest(records, name="Marathon", entered=595) is None

    def test_below_minimum_hidden(self):
        # Entered 10 with bias -10 -> 0 < 5: hidden.
        records = records_with(5, name="Quick", estimated=10, actual=1)
        # bias is -9 -> 10 - 9 = 1 -> rounds to 0
        assert suggest(records, name="Quick", entered=10) is None

    def test_at_maximum_still_shown(self):
        records = records_with(
            5, name="Marathon", estimated=570, actual=600
        )
        suggestion = suggest(records, name="Marathon", entered=570)
        assert suggestion is not None
        assert suggestion.suggested_minutes == 600


class TestCopy:
    def exact_suggestion(self):
        records = records_with(12, name="Algebra Test",
                               estimated=60, actual=70)
        return suggest(records, activity_type="Coding",
                       name="Algebra Test", entered=60)

    def test_headline_is_time_first(self):
        suggestion = self.exact_suggestion()
        assert suggestion.headline == "Ascend suggests ~70 min"

    def test_exact_evidence_copy_quotes_name(self):
        suggestion = self.exact_suggestion()
        assert suggestion.evidence_text == (
            'Based on 12 previous "Algebra Test" sessions.'
        )

    def test_category_evidence_copy(self):
        assert build_evidence_text(14, "category", "Coding", None) == (
            "Based on 14 previous Coding activities."
        )

    def test_overall_evidence_copy(self):
        assert build_evidence_text(46, "overall", None, None) == (
            "Based on 46 completed activities."
        )

    def test_difference_copy_positive(self):
        assert build_difference_text(10) == (
            "You typically take ~10 min longer."
        )

    def test_difference_copy_negative(self):
        assert build_difference_text(-5) == (
            "You typically finish ~5 min early."
        )

    def test_no_percent_or_multiplier_in_actionable_copy(self):
        suggestion = self.exact_suggestion()
        for text in (
            suggestion.headline,
            suggestion.difference_text,
            suggestion.evidence_text,
            suggestion.keep_label,
            suggestion.use_label,
        ):
            assert "%" not in text
            assert "×" not in text
            assert "x1." not in text.lower()

    def test_action_labels_are_concrete(self):
        suggestion = self.exact_suggestion()
        assert suggestion.keep_label == "Keep 60 min"
        assert suggestion.use_label == "Use 70 min"
