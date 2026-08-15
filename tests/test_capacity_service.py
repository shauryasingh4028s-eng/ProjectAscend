"""Planner Capacity Intelligence: the capacity calculation.

Pure unit tests over the Qt-free engine. Activities are plain Activity
objects, and the Smart Activity Estimate evidence is supplied as the
same record shape Database.get_calibration_records() returns, so the
frozen estimate layer is exercised through its real public API.
"""

import pytest

from Modules.activity import Activity
from Modules.capacity_service import (
    BASIS_LEARNED,
    BASIS_USER_ESTIMATE,
    ESTIMATE_MAX_MINUTES,
    ESTIMATE_MIN_MINUTES,
    NEAR_CAPACITY_MINUTES,
    STATE_NEAR_CAPACITY,
    STATE_NO_CAPACITY_DATA,
    STATE_NO_TASKS,
    STATE_OVER_CAPACITY,
    STATE_UNDER_CAPACITY,
    build_capacity_plan,
    select_move_candidates,
)


PLAN_DATE = "2026-08-16"


def task(name="Maths", estimated=60, activity_type="Homework",
         completed=False, actual=0, activity_id=None):
    return Activity(
        id=activity_id,
        date=PLAN_DATE,
        activity_type=activity_type,
        name=name,
        estimated_minutes=estimated,
        completed=completed,
        actual_minutes=actual,
    )


def observation(activity_type="Coding", name="Project",
                original=60, actual=70):
    """One completed plan-vs-actual record, as the database returns it."""
    return {
        "activity_id": 1,
        "activity_type": activity_type,
        "name": name,
        "original_estimate_minutes": original,
        "estimated_minutes": original,
        "completed": True,
        "actual_minutes": actual,
    }


def evidence(count, activity_type="Coding", name="Project",
             original=60, actual=70):
    return [
        observation(activity_type, name, original, actual)
        for _ in range(count)
    ]


def plan_for(tasks, available=None, records=None):
    return build_capacity_plan(tasks, available, records or [], PLAN_DATE)


class TestEmptyAndMissingInputs:
    def test_no_tasks_with_available_time(self):
        plan = plan_for([], available=180)

        assert plan.state == STATE_NO_TASKS
        assert plan.planned_workload_minutes == 0
        assert plan.expected_workload_minutes == 0
        assert plan.pending_task_count == 0

    def test_no_tasks_without_available_time(self):
        plan = plan_for([])

        assert plan.state == STATE_NO_CAPACITY_DATA
        assert plan.expected_workload_minutes == 0

    def test_no_available_time_produces_no_fit_verdict(self):
        plan = plan_for([task(estimated=60), task(estimated=45)])

        assert plan.state == STATE_NO_CAPACITY_DATA
        assert plan.available_minutes is None
        assert plan.remaining_capacity_minutes is None
        assert plan.open_capacity_minutes == 0
        assert plan.over_capacity_minutes == 0
        assert plan.fitting_task_count == 0
        assert all(not item.fits for item in plan.tasks)

    def test_workload_still_reported_without_available_time(self):
        plan = plan_for([task(estimated=60), task(estimated=45)])

        assert plan.planned_workload_minutes == 105
        assert plan.expected_workload_minutes == 105


class TestPlannedWorkload:
    def test_sum_of_user_estimates(self):
        plan = plan_for([
            task("Maths", 60),
            task("Science", 45),
            task("Coding", 70),
            task("English", 40),
        ])

        assert plan.planned_workload_minutes == 215

    def test_single_task(self):
        plan = plan_for([task(estimated=90)], available=180)

        assert plan.planned_workload_minutes == 90
        assert plan.expected_workload_minutes == 90
        assert plan.state == STATE_UNDER_CAPACITY

    def test_invalid_estimates_contribute_zero(self):
        plan = plan_for([task(estimated=0), task(estimated=-30)])

        assert plan.planned_workload_minutes == 0
        assert plan.expected_workload_minutes == 0


class TestExpectedWorkload:
    def test_without_evidence_expected_equals_planned(self):
        tasks = [task("Maths", 60), task("Science", 45)]
        plan = plan_for(tasks, available=180, records=[])

        assert plan.expected_workload_minutes == 105
        assert plan.planned_workload_minutes == 105
        assert plan.learned_adjustment_minutes == 0
        assert plan.learned_task_count == 0
        assert all(item.basis == BASIS_USER_ESTIMATE for item in plan.tasks)

    def test_records_none_falls_back_to_user_estimates(self):
        plan = build_capacity_plan(
            [task(estimated=60)], 180, None, PLAN_DATE
        )

        assert plan.expected_workload_minutes == 60
        assert plan.tasks[0].basis == BASIS_USER_ESTIMATE

    def test_learned_evidence_raises_expected_workload(self):
        # Five completed "Project" sessions at 60 planned / 70 actual
        # unlock the exact-activity tier: +10 min.
        records = evidence(5, "Coding", "Project", 60, 70)
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=180,
            records=records,
        )

        assert plan.planned_workload_minutes == 60
        assert plan.expected_workload_minutes == 70
        assert plan.learned_adjustment_minutes == 10
        assert plan.learned_task_count == 1
        assert plan.tasks[0].basis == BASIS_LEARNED

    def test_learned_evidence_can_lower_expected_workload(self):
        records = evidence(5, "Coding", "Project", 60, 50)
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=180,
            records=records,
        )

        assert plan.expected_workload_minutes == 50
        assert plan.learned_adjustment_minutes == -10

    def test_only_evidenced_tasks_are_adjusted(self):
        records = evidence(5, "Coding", "Project", 60, 70)
        plan = plan_for(
            [
                task("Project", 60, activity_type="Coding"),
                task("Essay", 40, activity_type="Writing"),
            ],
            available=300,
            records=records,
        )

        assert plan.planned_workload_minutes == 100
        assert plan.expected_workload_minutes == 110
        assert plan.learned_task_count == 1
        by_name = {item.name: item for item in plan.tasks}
        assert by_name["Project"].basis == BASIS_LEARNED
        assert by_name["Essay"].basis == BASIS_USER_ESTIMATE

    def test_learned_adjustment_matches_per_task_deltas(self):
        records = evidence(5, "Coding", "Project", 60, 70)
        plan = plan_for(
            [
                task("Project", 60, activity_type="Coding"),
                task("Essay", 40, activity_type="Writing"),
            ],
            available=300,
            records=records,
        )

        per_task = sum(
            item.expected_minutes - item.estimate_minutes
            for item in plan.tasks
        )
        assert plan.learned_adjustment_minutes == per_task


class TestCapacityStates:
    def test_over_capacity(self):
        plan = plan_for(
            [task(estimated=120), task(estimated=125)],
            available=180,
        )

        assert plan.state == STATE_OVER_CAPACITY
        assert plan.remaining_capacity_minutes == -65
        assert plan.over_capacity_minutes == 65
        assert plan.open_capacity_minutes == 0

    def test_under_capacity(self):
        plan = plan_for([task(estimated=140)], available=240)

        assert plan.state == STATE_UNDER_CAPACITY
        assert plan.remaining_capacity_minutes == 100
        assert plan.open_capacity_minutes == 100
        assert plan.over_capacity_minutes == 0

    def test_exactly_full_is_near_capacity_not_over(self):
        plan = plan_for([task(estimated=180)], available=180)

        assert plan.state == STATE_NEAR_CAPACITY
        assert plan.remaining_capacity_minutes == 0
        assert plan.over_capacity_minutes == 0
        assert plan.open_capacity_minutes == 0

    def test_fifteen_minutes_remaining_is_near_capacity(self):
        plan = plan_for([task(estimated=165)], available=180)

        assert plan.remaining_capacity_minutes == NEAR_CAPACITY_MINUTES
        assert plan.state == STATE_NEAR_CAPACITY

    def test_sixteen_minutes_remaining_is_under_capacity(self):
        plan = plan_for([task(estimated=164)], available=180)

        assert plan.remaining_capacity_minutes == 16
        assert plan.state == STATE_UNDER_CAPACITY

    def test_one_minute_over_is_over_capacity(self):
        plan = plan_for([task(estimated=181)], available=180)

        assert plan.state == STATE_OVER_CAPACITY
        assert plan.over_capacity_minutes == 1

    def test_zero_available_time_is_a_real_value(self):
        plan = plan_for([task(estimated=30)], available=0)

        assert plan.available_minutes == 0
        assert plan.state == STATE_OVER_CAPACITY
        assert plan.over_capacity_minutes == 30

    def test_zero_available_time_with_no_tasks(self):
        plan = plan_for([], available=0)

        assert plan.state == STATE_NO_TASKS

    def test_daily_goal_is_never_used_as_capacity(self):
        # A plan with no stated available time must not borrow any
        # target value: the verdict simply does not exist.
        plan = plan_for([task(estimated=60)])

        assert plan.available_minutes is None
        assert plan.state == STATE_NO_CAPACITY_DATA


class TestFitCalculation:
    def test_fit_follows_list_order(self):
        plan = plan_for(
            [
                task("First", 60),
                task("Second", 60),
                task("Third", 60),
                task("Fourth", 60),
            ],
            available=180,
        )

        assert [item.fits for item in plan.tasks] == [
            True, True, True, False
        ]
        assert plan.fitting_task_count == 3
        assert plan.beyond_task_count == 1

    def test_counts_always_cover_every_pending_task(self):
        plan = plan_for(
            [task("A", 50), task("B", 50), task("C", 50)],
            available=120,
        )

        assert (
            plan.fitting_task_count + plan.beyond_task_count
            == plan.pending_task_count
        )

    def test_a_later_short_task_does_not_jump_the_queue(self):
        # Once the running total passes the available time, everything
        # after it is beyond - the order the user chose is respected
        # rather than repacked into a "best fit". The trailing 10-minute
        # task would fit in the 10 minutes left, but promoting it would
        # silently reorder the user's plan.
        plan = plan_for(
            [task("Long", 100), task("Medium", 90), task("Short", 10)],
            available=110,
        )

        assert [item.fits for item in plan.tasks] == [True, False, False]
        assert plan.fitting_task_count == 1

    def test_all_tasks_fit_when_under_capacity(self):
        plan = plan_for([task("A", 30), task("B", 30)], available=240)

        assert plan.fitting_task_count == 2
        assert plan.beyond_task_count == 0

    def test_very_long_task_fits_nothing(self):
        plan = plan_for([task("Marathon", 600)], available=120)

        assert plan.state == STATE_OVER_CAPACITY
        assert plan.fitting_task_count == 0
        assert plan.beyond_task_count == 1
        assert plan.over_capacity_minutes == 480
        assert plan.open_capacity_minutes == 0

    def test_fit_uses_expected_not_planned_minutes(self):
        records = evidence(5, "Coding", "Project", 60, 70)
        # Two 60-minute tasks fit 130 minutes on the user's estimates,
        # but the learned durations (70 each) do not.
        plan = plan_for(
            [
                task("Project", 60, activity_type="Coding"),
                task("Project", 60, activity_type="Coding"),
            ],
            available=130,
            records=records,
        )

        assert plan.expected_workload_minutes == 140
        assert plan.state == STATE_OVER_CAPACITY
        assert plan.fitting_task_count == 1


class TestCompletedActivities:
    def test_completed_tasks_are_excluded_from_workload(self):
        plan = plan_for(
            [
                task("Done", 60, completed=True, actual=65),
                task("Pending", 45),
            ],
            available=180,
        )

        assert plan.planned_workload_minutes == 45
        assert plan.expected_workload_minutes == 45
        assert plan.pending_task_count == 1

    def test_completed_tasks_reported_separately(self):
        plan = plan_for(
            [
                task("Done", 60, completed=True, actual=65),
                task("Also done", 30, completed=True, actual=25),
                task("Pending", 45),
            ],
            available=180,
        )

        assert plan.completed_count == 2
        assert plan.completed_minutes == 90

    def test_all_tasks_completed_is_no_tasks(self):
        plan = plan_for(
            [task("Done", 60, completed=True, actual=60)],
            available=180,
        )

        assert plan.state == STATE_NO_TASKS
        assert plan.completed_count == 1

    def test_completed_work_does_not_consume_capacity(self):
        plan = plan_for(
            [
                task("Done", 120, completed=True, actual=120),
                task("Pending", 60),
            ],
            available=180,
        )

        assert plan.remaining_capacity_minutes == 120
        assert plan.state == STATE_UNDER_CAPACITY


class TestChangingAvailableTime:
    def test_same_plan_three_availabilities(self):
        tasks = [task("A", 90), task("B", 60)]

        tight = plan_for(tasks, available=120)
        exact = plan_for(tasks, available=150)
        roomy = plan_for(tasks, available=240)

        assert tight.state == STATE_OVER_CAPACITY
        assert tight.over_capacity_minutes == 30
        assert exact.state == STATE_NEAR_CAPACITY
        assert roomy.state == STATE_UNDER_CAPACITY
        assert roomy.open_capacity_minutes == 90

    def test_gaining_time_resolves_an_overload(self):
        tasks = [task("A", 150)]

        before = plan_for(tasks, available=120)
        after = plan_for(tasks, available=180)

        assert before.state == STATE_OVER_CAPACITY
        assert after.state == STATE_UNDER_CAPACITY

    def test_losing_time_creates_an_overload(self):
        tasks = [task("A", 200)]

        before = plan_for(tasks, available=240)
        after = plan_for(tasks, available=195)

        assert before.state == STATE_UNDER_CAPACITY
        assert after.state == STATE_OVER_CAPACITY
        assert after.over_capacity_minutes == 5

    def test_workload_is_independent_of_available_time(self):
        tasks = [task("A", 90), task("B", 60)]

        for available in (None, 0, 60, 150, 600):
            plan = plan_for(tasks, available=available)
            assert plan.planned_workload_minutes == 150
            assert plan.expected_workload_minutes == 150


class TestNonMutation:
    def test_inputs_are_never_modified(self):
        tasks = [
            task("Project", 60, activity_type="Coding"),
            task("Done", 30, completed=True, actual=35),
        ]
        records = evidence(5, "Coding", "Project", 60, 70)
        before = [
            (
                item.date,
                item.activity_type,
                item.name,
                item.estimated_minutes,
                item.completed,
                item.actual_minutes,
                item.original_estimate_minutes,
            )
            for item in tasks
        ]
        records_before = [dict(record) for record in records]

        build_capacity_plan(tasks, 180, records, PLAN_DATE)

        after = [
            (
                item.date,
                item.activity_type,
                item.name,
                item.estimated_minutes,
                item.completed,
                item.actual_minutes,
                item.original_estimate_minutes,
            )
            for item in tasks
        ]
        assert after == before
        assert records == records_before

    def test_task_list_is_not_reordered(self):
        tasks = [task("A", 60), task("B", 30), task("C", 90)]
        plan = plan_for(tasks, available=100)

        assert [item.name for item in plan.tasks] == ["A", "B", "C"]

    def test_repeated_calls_are_stable(self):
        tasks = [task("A", 60), task("B", 90)]

        first = plan_for(tasks, available=120)
        second = plan_for(tasks, available=120)

        assert first == second


class TestSmartEstimateIntegration:
    def test_planner_uses_the_dialog_bounds(self):
        assert ESTIMATE_MIN_MINUTES == 5
        assert ESTIMATE_MAX_MINUTES == 600

    def test_bounds_match_the_add_activity_dialog(self, qapp, database):
        from Dialogs.add_activity_dialog import AddActivityDialog

        dialog = AddActivityDialog(database, PLAN_DATE)
        try:
            assert dialog.estimated_time.minimum() == ESTIMATE_MIN_MINUTES
            assert dialog.estimated_time.maximum() == ESTIMATE_MAX_MINUTES
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_insufficient_evidence_is_not_applied(self):
        # Four observations sit below the exact-activity threshold of
        # five, and there is no category or overall fallback evidence.
        records = evidence(4, "Coding", "Project", 60, 70)
        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=180,
            records=records,
        )

        assert plan.expected_workload_minutes == 60
        assert plan.tasks[0].basis == BASIS_USER_ESTIMATE

    def test_incomplete_records_are_not_evidence(self):
        records = evidence(8, "Coding", "Project", 60, 70)
        for record in records:
            record["completed"] = False

        plan = plan_for(
            [task("Project", 60, activity_type="Coding")],
            available=180,
            records=records,
        )

        assert plan.expected_workload_minutes == 60

    def test_expected_value_is_never_written_back(self):
        activity = task("Project", 60, activity_type="Coding")
        records = evidence(5, "Coding", "Project", 60, 70)

        plan = plan_for([activity], available=180, records=records)

        assert plan.tasks[0].expected_minutes == 70
        # The activity itself keeps the user's own estimate: no feedback
        # loop back into the frozen estimate model.
        assert activity.estimated_minutes == 60


class TestMoveCandidates:
    def test_no_candidates_when_within_capacity(self):
        plan = plan_for([task("A", 60)], available=180)

        assert plan.move_candidates == ()

    def test_no_candidates_without_available_time(self):
        plan = plan_for([task("A", 600)])

        assert plan.move_candidates == ()

    def test_smallest_trailing_group_resolves_the_overload(self):
        plan = plan_for(
            [task("A", 60), task("B", 60), task("C", 60)],
            available=150,
        )

        assert [item.name for item in plan.move_candidates] == ["C"]

    def test_multiple_candidates_when_one_is_not_enough(self):
        # 60 + 30 + 30 against 70: dropping the last task alone still
        # leaves 90, so the trailing group grows to two.
        plan = plan_for(
            [task("A", 60), task("B", 30), task("C", 30)],
            available=70,
        )

        assert [item.name for item in plan.move_candidates] == ["B", "C"]

    def test_candidates_can_cover_every_task(self):
        # The first task alone already exceeds the available time, so no
        # trailing subset short of everything resolves the overload.
        plan = plan_for(
            [task("A", 120), task("B", 40), task("C", 40)],
            available=100,
        )

        assert [item.name for item in plan.move_candidates] == [
            "A", "B", "C"
        ]

    def test_helper_matches_the_plan(self):
        plan = plan_for(
            [task("A", 60), task("B", 60), task("C", 60)],
            available=150,
        )

        assert select_move_candidates(plan.tasks, 150) == plan.move_candidates
