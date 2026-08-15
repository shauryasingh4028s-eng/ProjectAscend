"""Planner Capacity Intelligence: the language rules.

Capacity is decision support, not a scoring system, and Ascend's
permanent time-first rule applies: percentages explain relationships,
time explains decisions. These tests hold the copy to both.
"""

import pytest

from Modules.activity import Activity
from Modules.capacity_service import (
    build_capacity_plan,
    build_headline,
    build_support_lines,
    format_capacity_duration,
)
from Modules.insights_service import format_minutes


PLAN_DATE = "2026-08-16"

# Guilt, enforcement and scoring language has no place in a planning
# aid, and no actionable capacity line may lean on a percentage.
BANNED_WORDS = (
    "behind",
    "failed",
    "should",
    "must",
    "only",
    "wasted",
    "overloaded",
)


def task(name="Maths", estimated=60, activity_type="Homework",
         completed=False, actual=0):
    return Activity(
        id=None,
        date=PLAN_DATE,
        activity_type=activity_type,
        name=name,
        estimated_minutes=estimated,
        completed=completed,
        actual_minutes=actual,
    )


def evidence(count, activity_type="Coding", name="Project",
             original=60, actual=70):
    return [
        {
            "activity_id": 1,
            "activity_type": activity_type,
            "name": name,
            "original_estimate_minutes": original,
            "estimated_minutes": original,
            "completed": True,
            "actual_minutes": actual,
        }
        for _ in range(count)
    ]


def plan_for(tasks, available=None, records=None):
    return build_capacity_plan(tasks, available, records or [], PLAN_DATE)


def all_copy(plan):
    return (build_headline(plan),) + build_support_lines(plan)


# Every capacity state, each with real copy to inspect.
def every_state_plan():
    tasks = [task("Maths", 60), task("Science", 45), task("Coding", 70)]
    return {
        "no_capacity_data": plan_for(tasks),
        "no_tasks": plan_for([], available=180),
        "no_tasks_completed": plan_for(
            [task("Done", 60, completed=True, actual=60)], available=180
        ),
        "under_capacity": plan_for(tasks, available=400),
        "near_capacity": plan_for(tasks, available=180),
        "exactly_full": plan_for(tasks, available=175),
        "over_capacity": plan_for(tasks, available=120),
        "learned": plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=120,
            records=evidence(5),
        ),
        "learned_early": plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=120,
            records=evidence(5, actual=50),
        ),
        "with_completed": plan_for(
            [
                task("Done", 60, completed=True, actual=65),
                task("Pending", 45),
            ],
            available=180,
        ),
        "zero_available": plan_for(tasks, available=0),
    }


ALL_PLANS = every_state_plan()


@pytest.mark.parametrize("state", sorted(ALL_PLANS))
class TestLanguageSafety:
    def test_no_percentages(self, state):
        for line in all_copy(ALL_PLANS[state]):
            assert "%" not in line, f"{state}: {line}"

    def test_no_percent_word(self, state):
        for line in all_copy(ALL_PLANS[state]):
            assert "percent" not in line.lower(), f"{state}: {line}"

    def test_no_banned_words(self, state):
        for line in all_copy(ALL_PLANS[state]):
            lowered = line.lower()
            for word in BANNED_WORDS:
                assert word not in lowered, f"{state}: {word} in {line}"

    def test_no_emoji_or_new_symbols(self, state):
        for line in all_copy(ALL_PLANS[state]):
            assert line.isprintable(), f"{state}: {line}"
            assert "!" not in line, f"{state}: {line}"

    def test_lines_are_non_empty(self, state):
        for line in all_copy(ALL_PLANS[state]):
            assert line.strip() == line
            assert line


class TestHedging:
    def test_learned_totals_are_hedged(self):
        plan = ALL_PLANS["learned"]
        text = " ".join(all_copy(plan))

        assert "about" in text.lower() or "~" in text

    def test_expected_workload_is_always_hedged(self):
        plan = ALL_PLANS["over_capacity"]
        balance = [
            line for line in build_support_lines(plan)
            if "Expected" in line
        ][0]

        assert "Expected ~" in balance

    def test_available_time_is_stated_as_fact(self):
        # The user's own stated time is a fact and carries no hedge,
        # while the expected workload beside it always does.
        plan = ALL_PLANS["over_capacity"]
        balance = [
            line for line in build_support_lines(plan)
            if line.startswith("Available")
        ][0]

        assert balance.startswith(
            f"Available {format_capacity_duration(plan.available_minutes)}"
        )
        assert "Available ~" not in balance
        assert "Available about" not in balance

    def test_learned_explanation_is_hedged(self):
        plan = ALL_PLANS["learned"]
        evidence_line = [
            line for line in build_support_lines(plan)
            if "history" in line
        ][0]

        assert evidence_line == (
            "Your history suggests ~10m more for this plan."
        )

    def test_over_capacity_amount_is_hedged(self):
        headline = build_headline(ALL_PLANS["over_capacity"])

        assert headline.startswith("This plan is about ")


class TestTimeFirstFormatting:
    def test_durations_use_the_shared_duration_format(self):
        plan = ALL_PLANS["over_capacity"]

        assert format_capacity_duration(
            plan.over_capacity_minutes
        ) in build_headline(plan)
        joined = " ".join(build_support_lines(plan))
        assert format_capacity_duration(plan.available_minutes) in joined
        assert format_capacity_duration(
            plan.expected_workload_minutes
        ) in joined

    def test_whole_hours_drop_the_zero_minutes(self):
        # "1h" scans better than "1h 0m"; every other duration is
        # delegated to the shared formatter unchanged.
        assert format_capacity_duration(60) == "1h"
        assert format_capacity_duration(180) == "3h"
        assert format_capacity_duration(70) == format_minutes(70) == "1h 10m"
        assert format_capacity_duration(45) == format_minutes(45) == "45m"
        assert format_capacity_duration(0) == format_minutes(0) == "0m"

    def test_open_capacity_reported_in_time(self):
        plan = ALL_PLANS["under_capacity"]
        headline = build_headline(plan)

        assert format_capacity_duration(
            plan.open_capacity_minutes
        ) in headline
        assert "open capacity" in headline

    def test_workload_reported_in_time_without_available_time(self):
        plan = ALL_PLANS["no_capacity_data"]
        headline = build_headline(plan)

        assert format_capacity_duration(
            plan.expected_workload_minutes
        ) in headline

    def test_completed_line_uses_time_and_counts(self):
        plan = ALL_PLANS["with_completed"]
        completed_line = [
            line for line in build_support_lines(plan)
            if "complete" in line
        ][0]

        assert "1 activity already complete (1h 5m)." == completed_line


class TestFitLanguage:
    def test_ordering_rule_is_never_exposed(self):
        # The list order remains the internal rule for calculating the
        # fit, but it is an implementation detail, not card copy.
        for plan in ALL_PLANS.values():
            text = " ".join(all_copy(plan)).lower()
            assert "based on the order" not in text
            assert "listed" not in text

    def test_fit_line_uses_task_counts(self):
        plan = plan_for(
            [task("A", 60), task("B", 60), task("C", 60), task("D", 60)],
            available=180,
        )
        fit_line = [
            line for line in build_support_lines(plan)
            if "beyond." in line
        ][0]

        assert fit_line == (
            "3 activities fit within your available time; 1 goes beyond."
        )

    def test_singular_and_plural_agree(self):
        plan = plan_for(
            [task("A", 100), task("B", 100), task("C", 100)],
            available=100,
        )
        fit_line = [
            line for line in build_support_lines(plan)
            if "beyond." in line
        ][0]

        assert fit_line == (
            "1 activity fits within your available time; 2 go beyond."
        )

    def test_single_task_over_capacity_has_no_fit_line(self):
        # "0 fit; 1 goes beyond" only restates the headline.
        plan = plan_for([task("A", 120)], available=60)

        assert plan.state == "over_capacity"
        assert not any(
            "beyond your available time" not in line and "fit" in line
            for line in build_support_lines(plan)
        )

    def test_nothing_fitting_has_no_fit_line(self):
        # The headline already says the whole plan is beyond the time.
        plan = plan_for([task("A", 120), task("B", 120)], available=60)

        assert plan.fitting_task_count == 0
        assert not any(
            "beyond." in line for line in build_support_lines(plan)
        )

    def test_no_fit_line_without_available_time(self):
        plan = ALL_PLANS["no_capacity_data"]

        assert not any(
            "beyond." in line for line in build_support_lines(plan)
        )

    def test_under_capacity_has_no_fit_line(self):
        plan = ALL_PLANS["under_capacity"]

        assert not any(
            "beyond." in line for line in build_support_lines(plan)
        )


class TestStateCopy:
    def test_no_capacity_data_invites_the_input(self):
        plan = ALL_PLANS["no_capacity_data"]

        assert build_headline(plan) == (
            "About 2h 55m of expected work planned."
        )
        assert len(build_support_lines(plan)) == 1
        assert (
            "Add the time you have available to see how it fits."
            in build_support_lines(plan)
        )

    def test_no_capacity_data_never_mentions_a_goal(self):
        text = " ".join(all_copy(ALL_PLANS["no_capacity_data"])).lower()

        assert "goal" not in text

    def test_no_tasks_does_not_ask_for_work(self):
        plan = ALL_PLANS["no_tasks"]
        text = " ".join(all_copy(plan)).lower()

        assert build_headline(plan) == "Nothing planned yet."
        assert "add an activity" not in text
        assert "you have 3h available." in text

    def test_completed_day_is_neutral(self):
        plan = ALL_PLANS["no_tasks_completed"]

        assert build_headline(plan) == "Everything planned is complete."

    def test_under_capacity_does_not_urge_filling_the_time(self):
        text = " ".join(all_copy(ALL_PLANS["under_capacity"])).lower()

        for phrase in ("add more", "fill", "you could fit", "why not"):
            assert phrase not in text

    def test_near_capacity_is_calm(self):
        plan = ALL_PLANS["near_capacity"]

        assert build_headline(plan) == (
            "This plan uses almost all of your available time."
        )

    def test_exactly_full_reads_naturally(self):
        plan = ALL_PLANS["exactly_full"]

        assert plan.open_capacity_minutes == 0
        assert "That fills the time you have." in build_support_lines(plan)

    def test_over_capacity_states_the_gap_in_time(self):
        plan = ALL_PLANS["over_capacity"]

        assert build_headline(plan) == (
            "This plan is about 55m beyond your available time."
        )

    def test_evidence_counts_are_never_exposed(self):
        # How many activities carried learned evidence is an internal
        # detail of the engine, not something the card reports.
        for plan in ALL_PLANS.values():
            text = " ".join(all_copy(plan))
            assert "of 1 activity use" not in text
            assert "use durations learned" not in text
            assert "add up to" not in text

    def test_learned_explanation_reports_more(self):
        plan = ALL_PLANS["learned"]

        assert (
            "Your history suggests ~10m more for this plan."
            in build_support_lines(plan)
        )

    def test_learned_explanation_reports_less(self):
        plan = ALL_PLANS["learned_early"]

        assert (
            "Your history suggests ~10m less for this plan."
            in build_support_lines(plan)
        )

    def test_learned_explanation_uses_suggests_not_adds(self):
        # "suggests" keeps the number a learned estimate rather than a
        # factual guarantee.
        plan = ALL_PLANS["learned"]
        text = " ".join(build_support_lines(plan))

        assert "suggests" in text
        assert "adds" not in text

    def test_no_explanation_when_nothing_was_learned(self):
        plan = ALL_PLANS["over_capacity"]
        text = " ".join(build_support_lines(plan))

        assert "history" not in text
        assert "Based on your own estimates." not in text

    def test_zero_adjustment_produces_no_explanation(self):
        # An expectation equal to the user's own estimates has nothing
        # to explain, and must never read as "~0m more".
        records = evidence(5, "Coding", "Project", 60, 70)
        plan = plan_for(
            [
                task("Project", 60, activity_type="Coding"),
                # A learned +10 cancelled by a learned -10.
                task("Essay", 60, activity_type="Writing"),
            ],
            available=180,
            records=records + evidence(5, "Writing", "Essay", 60, 50),
        )

        assert plan.learned_task_count == 2
        assert plan.learned_adjustment_minutes == 0
        text = " ".join(build_support_lines(plan))
        assert "history" not in text
        assert "~0m" not in text

    def test_no_zero_minute_explanation_anywhere(self):
        for plan in ALL_PLANS.values():
            text = " ".join(all_copy(plan))
            assert "~0m more" not in text
            assert "~0m less" not in text
            assert "about the same" not in text

class TestConciseness:
    """The card communicates a decision, not the calculation."""

    # DECISION + KEY NUMBERS + BRIEF EXPLANATION + at most one more.
    MAX_SUPPORT_LINES = 3

    @pytest.mark.parametrize("state", sorted(ALL_PLANS))
    def test_card_stays_scannable(self, state):
        plan = ALL_PLANS[state]

        assert len(build_support_lines(plan)) <= self.MAX_SUPPORT_LINES

    @pytest.mark.parametrize("state", sorted(ALL_PLANS))
    def test_every_line_is_a_single_short_sentence(self, state):
        for line in all_copy(ALL_PLANS[state]):
            # The diagnostic style joined several facts with ";" and
            # ran two sentences together in one line.
            assert ";" not in line or "beyond." in line
            assert len(line) <= 80, line

    def test_windows_acceptance_scenario(self):
        # Available 60, user estimate 60, learned expectation 70.
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=60,
            records=evidence(5),
        )

        assert build_headline(plan) == (
            "This plan is about 10m beyond your available time."
        )
        assert build_support_lines(plan) == (
            "Available 1h · Expected ~1h 10m",
            "Your history suggests ~10m more for this plan.",
        )

    def test_no_capacity_state_is_two_lines(self):
        plan = ALL_PLANS["no_capacity_data"]

        assert build_support_lines(plan) == (
            "Add the time you have available to see how it fits.",
        )

    def test_under_capacity_state_is_concise(self):
        plan = ALL_PLANS["under_capacity"]

        assert build_support_lines(plan) == (
            "Available 6h 40m · Expected ~2h 55m",
        )

    def test_near_capacity_state_is_concise(self):
        plan = ALL_PLANS["near_capacity"]

        assert build_support_lines(plan) == (
            "Available 3h · Expected ~2h 55m",
            "About 5m spare.",
        )

    def test_no_tasks_state_is_concise(self):
        plan = ALL_PLANS["no_tasks"]

        assert build_support_lines(plan) == ("You have 3h available.",)


class TestInformationSeparation:
    """Fact, learned expectation, explanation and decision stay apart."""

    def test_each_concept_has_its_own_line(self):
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=60,
            records=evidence(5),
        )
        headline = build_headline(plan)
        balance, explanation = build_support_lines(plan)

        # DECISION
        assert "beyond your available time" in headline
        # FACT and LEARNED EXPECTATION, clearly distinguished
        assert balance.startswith("Available 1h")
        assert "Expected ~1h 10m" in balance
        # LEARNED EXPLANATION
        assert explanation.startswith("Your history suggests")

    def test_explanation_is_not_merged_into_the_numbers(self):
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=60,
            records=evidence(5),
        )
        balance = build_support_lines(plan)[0]

        assert "history" not in balance


class TestUserControl:
    def test_no_recommendation_to_move_anything(self):
        # The engine may calculate a candidate, but no copy proposes an
        # action on a task in v1.4 #2.
        for plan in ALL_PLANS.values():
            text = " ".join(all_copy(plan)).lower()
            for phrase in ("move ", "reschedule", "delete", "remove "):
                assert phrase not in text
