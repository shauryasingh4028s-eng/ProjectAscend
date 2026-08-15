"""Planner Capacity Intelligence: planned workload vs realistic capacity.

Ascend is deliberately task-based rather than a fixed timetable, so this
layer does not generate a schedule. It answers one question and hands
the decision back to the user:

    How much work is planned, how much time is actually available, and
    how do those two compare?

Four DISTINCT concepts
----------------------
They are never merged, and never substituted for one another:

1. Daily goal (``settings.daily_goal``)
       An achievement TARGET measured on completed focus time. It drives
       streaks, the dashboard progress bar and goal insights. It says
       nothing about how much time the user actually has on a given day,
       so this module never reads it.

2. Planned workload
       FACT. The sum of the user's own estimates for the pending
       activities on a date.

3. Expected workload
       LEARNED ESTIMATE. The planned workload after Smart Activity
       Estimates replaces individual durations where - and only where -
       that frozen layer has reliable evidence for that activity.

4. Available capacity
       The user's own STATED minutes for that date. Explicitly entered,
       never derived, never guessed, never defaulted.

Relationship to Smart Activity Estimates (frozen, v1.4 #1)
----------------------------------------------------------
This module CONSUMES ``suggest_estimate`` and nothing else. Medians,
evidence tiers, relevance windows, rounding and identity suppression all
stay the property of ``Modules/estimate_suggestion.py``; none of it is
reimplemented here. The same 5-600 minute bounds the Add Activity dialog
uses are passed through, so a task is evaluated exactly as it would be
in that dialog.

The learned duration is used for DISPLAY AND ARITHMETIC ONLY. Nothing is
ever written back to an activity, so an expected value can never become
evidence the estimate model later learns from - the no-feedback-loop
guarantee of Smart Activity Estimates is preserved by construction.

Product safeguards owned by this layer
--------------------------------------
* Facts and learned estimates are reported separately and labelled
  differently, so "over capacity" is always explainable.
* Without stated available time NO fit verdict is produced at all. The
  daily goal is never borrowed as a stand-in.
* Recommendations are advisory. This module returns numbers and copy; it
  never moves, edits, reorders, completes or deletes anything, and the
  planner offers no action that does.
* Ordering is the user's own insertion order, and every fit statement
  says so. Priority is never inferred from category, name, duration or
  history, because no priority signal exists in the data model.
* Time-first copy: concrete minutes and hours, task counts, no
  percentages in any actionable string.

The module is Qt-free so the decision logic is fully testable without a
GUI environment.
"""

from dataclasses import dataclass

from Modules.estimate_suggestion import suggest_estimate
from Modules.insights_service import format_minutes


# ---------------------------------------------------------------------------
# Estimate bounds.
#
# These mirror the AddActivityDialog QSpinBox range exactly. Passing the
# dialog's own bounds keeps Smart Activity Estimates' tier selection,
# relevance window and range-honesty behaviour identical between the
# dialog and the planner: a task is never evaluated differently here.
# ---------------------------------------------------------------------------

ESTIMATE_MIN_MINUTES = 5
ESTIMATE_MAX_MINUTES = 600

# ---------------------------------------------------------------------------
# Near-capacity band.
#
# A PRODUCT SAFEGUARD in the same spirit as the calibration engine's
# documented thresholds, not a scientific claim. Three 5-minute planner
# steps: inside this band a plan is neither comfortably under nor
# meaningfully over its available time, and Ascend says exactly that
# instead of implying precision it does not have.
#
# A plan that exactly fills the available time is therefore "near
# capacity", never "over capacity".
# ---------------------------------------------------------------------------

NEAR_CAPACITY_MINUTES = 15


# Capacity states.
STATE_NO_CAPACITY_DATA = "no_capacity_data"
STATE_NO_TASKS = "no_tasks"
STATE_UNDER_CAPACITY = "under_capacity"
STATE_NEAR_CAPACITY = "near_capacity"
STATE_OVER_CAPACITY = "over_capacity"

# How an activity's expected duration was arrived at.
BASIS_LEARNED = "learned"
BASIS_USER_ESTIMATE = "your_estimate"


@dataclass(frozen=True)
class TaskLoad:
    """One activity's contribution to the day's workload."""

    activity_id: int | None
    name: str
    activity_type: str
    # The user's own estimate. A fact.
    estimate_minutes: int
    # What the plan is expected to cost. Equal to estimate_minutes
    # unless Smart Activity Estimates had reliable evidence.
    expected_minutes: int
    # "learned" | "your_estimate"
    basis: str
    completed: bool
    # Whether this activity falls inside the available time when the
    # list is walked in the user's own order. Always False when no
    # available time has been stated.
    fits: bool


@dataclass(frozen=True)
class CapacityPlan:
    """The complete capacity picture for one planned date."""

    plan_date: str
    # no_capacity_data | no_tasks | under_capacity | near_capacity |
    # over_capacity
    state: str
    # Pending activities only, in the user's own order.
    tasks: tuple[TaskLoad, ...]

    # Completed work is reported separately: its time is spent, not
    # planned, so it never enters the workload totals.
    completed_count: int
    completed_minutes: int

    # FACT: the sum of the user's estimates for pending activities.
    planned_workload_minutes: int
    # LEARNED ESTIMATE: the same plan after Smart Activity Estimates.
    expected_workload_minutes: int
    # Signed difference between the two above. The explainability hook.
    learned_adjustment_minutes: int
    # How many pending activities used a learned duration.
    learned_task_count: int

    # The user's stated available time, or None when not stated.
    available_minutes: int | None
    # available - expected. None when no available time was stated.
    remaining_capacity_minutes: int | None
    open_capacity_minutes: int
    over_capacity_minutes: int

    fitting_task_count: int
    beyond_task_count: int
    # Calculated for future extensibility. v1.4 #2 exposes NO move
    # action in the UI; nothing is ever moved automatically.
    move_candidates: tuple[TaskLoad, ...]

    @property
    def pending_task_count(self):
        return len(self.tasks)

    @property
    def has_available_time(self):
        return self.available_minutes is not None


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------


def expected_minutes_for(activity, records):
    """Return ``(expected_minutes, basis)`` for one planned activity.

    Smart Activity Estimates is consulted through its public API only.
    When it has no reliable evidence for this activity - or suppresses a
    suggestion as noise, or hides one outside the valid range - the
    user's own estimate is used unchanged. Ascend never inflates an
    unsupported estimate "to be safe".
    """
    estimate = max(0, int(activity.estimated_minutes or 0))

    suggestion = suggest_estimate(
        records or [],
        activity.activity_type,
        activity.name,
        estimate,
        ESTIMATE_MIN_MINUTES,
        ESTIMATE_MAX_MINUTES,
    )

    if suggestion is None:
        return estimate, BASIS_USER_ESTIMATE

    return suggestion.suggested_minutes, BASIS_LEARNED


def classify_state(available_minutes, pending_count, remaining_minutes):
    """Map the calculated numbers onto one capacity state.

    Without stated available time there is no verdict to give, so that
    check comes first: Ascend would rather say nothing than guess.
    """
    if available_minutes is None:
        return STATE_NO_CAPACITY_DATA
    if pending_count == 0:
        return STATE_NO_TASKS
    if remaining_minutes < 0:
        return STATE_OVER_CAPACITY
    if remaining_minutes <= NEAR_CAPACITY_MINUTES:
        return STATE_NEAR_CAPACITY
    return STATE_UNDER_CAPACITY


def select_move_candidates(tasks, available_minutes):
    """Return the smallest trailing group whose removal would bring the
    plan inside the available time.

    Calculated for future extensibility and for tests. v1.4 #2 shows no
    move action: the planner never offers to move a task, and this layer
    never moves one.
    """
    if available_minutes is None:
        return ()

    total = sum(task.expected_minutes for task in tasks)
    if total <= available_minutes:
        return ()

    candidates = []
    for task in reversed(tasks):
        candidates.append(task)
        total -= task.expected_minutes
        if total <= available_minutes:
            break

    return tuple(reversed(candidates))


def build_capacity_plan(activities, available_minutes, records, plan_date):
    """Build the complete capacity picture for one date.

    A pure function of its inputs: the same activities, available time
    and history always produce the same result, and nothing is cached.
    That is what makes capacity adaptive - when the user gains or loses
    an hour, only the available-time input changes and the whole picture
    is simply recalculated. The plan itself is never rebuilt or touched.

    The passed-in activities are never mutated.
    """
    activities = list(activities or [])

    completed = [activity for activity in activities if activity.completed]
    pending = [activity for activity in activities if not activity.completed]

    completed_minutes = sum(
        max(0, int(activity.actual_minutes or 0)) for activity in completed
    )

    # ------------------------------------------------------------------
    # Per-activity durations. The history snapshot is read once by the
    # caller and reused for every activity - no per-task query.
    # ------------------------------------------------------------------
    loads = []
    for activity in pending:
        estimate = max(0, int(activity.estimated_minutes or 0))
        expected, basis = expected_minutes_for(activity, records)
        loads.append(
            TaskLoad(
                activity_id=activity.id,
                name=activity.name,
                activity_type=activity.activity_type,
                estimate_minutes=estimate,
                expected_minutes=expected,
                basis=basis,
                completed=False,
                # Replaced below once available time is known.
                fits=False,
            )
        )

    planned_workload = sum(load.estimate_minutes for load in loads)
    expected_workload = sum(load.expected_minutes for load in loads)
    learned_adjustment = expected_workload - planned_workload
    learned_task_count = sum(
        1 for load in loads if load.basis == BASIS_LEARNED
    )

    # ------------------------------------------------------------------
    # Fit, in the user's own order.
    #
    # Insertion order (the order shown on screen) is the only ordering
    # signal that exists in the data model, and it is a real user
    # signal. Priority is never inferred, so every fit statement names
    # the basis it used.
    # ------------------------------------------------------------------
    if available_minutes is None:
        tasks = tuple(loads)
        fitting_count = 0
        remaining_capacity = None
        open_capacity = 0
        over_capacity = 0
    else:
        running_total = 0
        still_fitting = True
        placed = []
        for load in loads:
            running_total += load.expected_minutes
            if still_fitting and running_total <= available_minutes:
                fits = True
            else:
                fits = False
                still_fitting = False
            placed.append(
                TaskLoad(
                    activity_id=load.activity_id,
                    name=load.name,
                    activity_type=load.activity_type,
                    estimate_minutes=load.estimate_minutes,
                    expected_minutes=load.expected_minutes,
                    basis=load.basis,
                    completed=load.completed,
                    fits=fits,
                )
            )
        tasks = tuple(placed)
        fitting_count = sum(1 for task in tasks if task.fits)
        remaining_capacity = available_minutes - expected_workload
        open_capacity = max(0, remaining_capacity)
        over_capacity = max(0, -remaining_capacity)

    state = classify_state(available_minutes, len(tasks), remaining_capacity)

    return CapacityPlan(
        plan_date=plan_date,
        state=state,
        tasks=tasks,
        completed_count=len(completed),
        completed_minutes=completed_minutes,
        planned_workload_minutes=planned_workload,
        expected_workload_minutes=expected_workload,
        learned_adjustment_minutes=learned_adjustment,
        learned_task_count=learned_task_count,
        available_minutes=available_minutes,
        remaining_capacity_minutes=remaining_capacity,
        open_capacity_minutes=open_capacity,
        over_capacity_minutes=over_capacity,
        fitting_task_count=fitting_count,
        beyond_task_count=len(tasks) - fitting_count,
        move_candidates=select_move_candidates(tasks, available_minutes),
    )


# ---------------------------------------------------------------------------
# Copy.
#
# Time-first: minutes, hours and task counts. Never percentages in an
# actionable line. Facts are stated plainly; learned values always carry
# an "about", so an inference is never presented as a certainty. The
# tone is neutral throughout - capacity is decision support, not a score.
# ---------------------------------------------------------------------------


def activity_noun(count):
    return "activity" if count == 1 else "activities"


def build_headline(plan):
    """The one line that states the situation."""
    if plan.state == STATE_NO_TASKS:
        if plan.completed_count > 0:
            return "Everything planned is complete."
        return "Nothing planned yet."

    if plan.state == STATE_NO_CAPACITY_DATA:
        if not plan.tasks:
            if plan.completed_count > 0:
                return "Everything planned is complete."
            return "Nothing planned yet."
        return (
            f"About {format_minutes(plan.expected_workload_minutes)} "
            "of expected work planned."
        )

    if plan.state == STATE_OVER_CAPACITY:
        return (
            f"This plan is about "
            f"{format_minutes(plan.over_capacity_minutes)} beyond your "
            "available time."
        )

    if plan.state == STATE_NEAR_CAPACITY:
        return "This plan uses almost all of your available time."

    return (
        f"You have about {format_minutes(plan.open_capacity_minutes)} "
        "of open capacity."
    )


def build_balance_line(plan):
    """The supporting fact line: stated time against expected work."""
    if plan.state == STATE_NO_CAPACITY_DATA:
        return "Add the time you have available to see how it fits."

    if plan.available_minutes is None:
        return ""

    available_text = f"Available {format_minutes(plan.available_minutes)}"

    if plan.state == STATE_NO_TASKS:
        return f"You have {format_minutes(plan.available_minutes)} available."

    return (
        f"{available_text} · Expected about "
        f"{format_minutes(plan.expected_workload_minutes)}"
    )


def build_evidence_line(plan):
    """Explain where the expected number came from.

    Separates the factual sum of the user's estimates from the learned
    adjustment, and names how many activities the learning covered, so
    "expected" is always traceable.
    """
    if not plan.tasks:
        return ""

    estimates_text = (
        f"Your estimates add up to "
        f"{format_minutes(plan.planned_workload_minutes)}"
    )

    if plan.learned_task_count == 0:
        # Nothing was learned for this plan, so the expected total is
        # simply the user's own arithmetic. Saying so is clearer than
        # repeating the same number as if it were a finding.
        return "Based on your own estimates."

    covered = (
        f"{plan.learned_task_count} of {len(plan.tasks)} "
        f"{activity_noun(len(plan.tasks))} use durations learned from "
        "your history."
    )

    if plan.learned_adjustment_minutes > 0:
        adjustment = (
            f"; your history suggests about "
            f"{format_minutes(plan.learned_adjustment_minutes)} more"
        )
    elif plan.learned_adjustment_minutes < 0:
        adjustment = (
            f"; your history suggests about "
            f"{format_minutes(-plan.learned_adjustment_minutes)} less"
        )
    else:
        adjustment = "; your history suggests about the same"

    return f"{estimates_text}{adjustment}. {covered}"


def build_fit_line(plan):
    """State which activities fit, always naming the ordering used."""
    if plan.available_minutes is None or not plan.tasks:
        return ""

    if plan.state == STATE_OVER_CAPACITY:
        return (
            f"{plan.fitting_task_count} "
            f"{activity_noun(plan.fitting_task_count)} fit; "
            f"{plan.beyond_task_count} would go beyond, based on the "
            "order they're listed."
        )

    if plan.state == STATE_NEAR_CAPACITY:
        if plan.open_capacity_minutes == 0:
            return "That fills the time you have."
        return f"About {format_minutes(plan.open_capacity_minutes)} spare."

    return ""


def build_completed_line(plan):
    """Completed work, reported separately from the planned workload."""
    if plan.completed_count == 0:
        return ""

    return (
        f"{plan.completed_count} "
        f"{activity_noun(plan.completed_count)} already complete "
        f"({format_minutes(plan.completed_minutes)})."
    )


def build_support_lines(plan):
    """All supporting lines for the capacity card, in display order."""
    lines = (
        build_balance_line(plan),
        build_evidence_line(plan),
        build_fit_line(plan),
        build_completed_line(plan),
    )
    return tuple(line for line in lines if line)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CapacityService:
    """Build the capacity picture for a date from persisted data.

    Read-only with respect to activities and all analytics data. The one
    and only value it ever writes is the available time the user
    explicitly entered, through AvailableTimeStore.
    """

    def __init__(self, database, available_time_store=None):
        from Modules.available_time_store import AvailableTimeStore

        self.database = database
        self.available_time_store = (
            available_time_store or AvailableTimeStore(database)
        )

    def build_plan(self, plan_date):
        """Return the CapacityPlan for one date.

        Two reads, zero writes: the planned activities for the date and
        one snapshot of the historical plan-vs-actual records that Smart
        Activity Estimates needs. The snapshot is reused for every
        activity.
        """
        activities = self.database.get_activities_for_date(plan_date)
        records = self.load_calibration_records()
        available_minutes = self.get_available_minutes(plan_date)

        return build_capacity_plan(
            activities,
            available_minutes,
            records,
            plan_date,
        )

    def load_calibration_records(self):
        """Read the historical records, or ``None`` when unavailable.

        Mirrors the Add Activity dialog's defensive read: the planner
        must never fail to render because estimate evidence could not be
        loaded. Without records every activity simply uses the user's
        own estimate.
        """
        try:
            return self.database.get_calibration_records()
        except Exception:
            return None

    def get_available_minutes(self, plan_date):
        return self.available_time_store.get(plan_date)

    def set_available_minutes(self, plan_date, minutes):
        """Persist the available time the user explicitly entered."""
        return self.available_time_store.set(plan_date, minutes)

    def clear_available_minutes(self, plan_date):
        """Forget a date's available time, returning the planner to the
        "no available-time information" state."""
        self.available_time_store.clear(plan_date)
