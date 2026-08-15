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

        assert "about" in text.lower()

    def test_expected_workload_is_always_hedged(self):
        plan = ALL_PLANS["over_capacity"]
        balance = [
            line for line in build_support_lines(plan)
            if "Expected" in line
        ][0]

        assert "Expected about" in balance

    def test_available_time_is_stated_as_fact(self):
        # The user's own stated time is a fact and carries no hedge.
        plan = ALL_PLANS["over_capacity"]
        balance = [
            line for line in build_support_lines(plan)
            if line.startswith("Available")
        ][0]

        assert balance.startswith(
            f"Available {format_minutes(plan.available_minutes)}"
        )
        assert "Available about" not in balance

    def test_user_estimate_sum_is_stated_as_fact(self):
        plan = ALL_PLANS["learned"]
        evidence_line = [
            line for line in build_support_lines(plan)
            if "estimates add up to" in line
        ][0]

        assert "Your estimates add up to 1h 0m" in evidence_line
        assert "add up to about" not in evidence_line

    def test_over_capacity_amount_is_hedged(self):
        headline = build_headline(ALL_PLANS["over_capacity"])

        assert headline.startswith("This plan is about ")


class TestTimeFirstFormatting:
    def test_durations_use_format_minutes(self):
        plan = ALL_PLANS["over_capacity"]

        assert format_minutes(plan.over_capacity_minutes) in build_headline(
            plan
        )
        joined = " ".join(build_support_lines(plan))
        assert format_minutes(plan.available_minutes) in joined
        assert format_minutes(plan.expected_workload_minutes) in joined

    def test_open_capacity_reported_in_time(self):
        plan = ALL_PLANS["under_capacity"]
        headline = build_headline(plan)

        assert format_minutes(plan.open_capacity_minutes) in headline
        assert "open capacity" in headline

    def test_workload_reported_in_time_without_available_time(self):
        plan = ALL_PLANS["no_capacity_data"]
        headline = build_headline(plan)

        assert format_minutes(plan.expected_workload_minutes) in headline

    def test_completed_line_uses_time_and_counts(self):
        plan = ALL_PLANS["with_completed"]
        completed_line = [
            line for line in build_support_lines(plan)
            if "complete" in line
        ][0]

        assert "1 activity already complete (1h 5m)." == completed_line


class TestFitLanguage:
    def test_fit_line_names_the_ordering(self):
        plan = ALL_PLANS["over_capacity"]
        fit_line = [
            line for line in build_support_lines(plan)
            if "would go beyond" in line
        ][0]

        assert "based on the order they're listed" in fit_line

    def test_fit_line_uses_task_counts(self):
        plan = plan_for(
            [task("A", 60), task("B", 60), task("C", 60), task("D", 60)],
            available=180,
        )
        fit_line = [
            line for line in build_support_lines(plan)
            if "would go beyond" in line
        ][0]

        assert fit_line.startswith("3 activities fit; 1 would go beyond")

    def test_singular_activity_wording(self):
        plan = plan_for(
            [task("A", 100), task("B", 100)],
            available=100,
        )
        fit_line = [
            line for line in build_support_lines(plan)
            if "would go beyond" in line
        ][0]

        assert fit_line.startswith("1 activity fit")

    def test_no_fit_line_without_available_time(self):
        plan = ALL_PLANS["no_capacity_data"]

        assert not any(
            "go beyond" in line for line in build_support_lines(plan)
        )


class TestStateCopy:
    def test_no_capacity_data_invites_the_input(self):
        plan = ALL_PLANS["no_capacity_data"]

        assert build_headline(plan) == (
            "About 2h 55m of expected work planned."
        )
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
        assert "you have 3h 0m available." in text

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

    def test_evidence_line_names_how_many_tasks_were_learned(self):
        plan = ALL_PLANS["learned"]
        evidence_line = [
            line for line in build_support_lines(plan)
            if "learned from your history" in line
        ][0]

        assert "1 of 1 activity use" in evidence_line

    def test_evidence_line_reports_a_smaller_expectation(self):
        plan = ALL_PLANS["learned_early"]
        text = " ".join(build_support_lines(plan))

        assert "your history suggests about 10m less" in text

    def test_evidence_line_without_learning_says_so(self):
        plan = ALL_PLANS["over_capacity"]

        assert "Based on your own estimates." in build_support_lines(plan)

    def test_no_recommendation_to_move_anything(self):
        # The engine may calculate a candidate, but no copy proposes an
        # action on a task in v1.4 #2.
        for plan in ALL_PLANS.values():
            text = " ".join(all_copy(plan)).lower()
            for phrase in ("move ", "reschedule", "delete", "remove "):
                assert phrase not in text
