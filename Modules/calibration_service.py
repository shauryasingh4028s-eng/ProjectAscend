"""Estimate calibration for Project Ascend.

Measures how the user's planned durations compare with what actually
happened, both overall and per activity category.

Product philosophy
------------------
This layer is deliberately transparent and conservative:

* Every number is a plain statistic over completed activities - no machine
  learning, no external services, no hidden models.
* Invalid or incomplete records are skipped, never silently replaced with
  invented values.
* The system refuses to make recommendations until enough completed
  observations exist. Saying "not enough data yet" is a feature, not a
  failure.

Terminology
-----------
* relative error  = (actual - estimated) / estimated. Positive means the
  work took LONGER than planned (the estimate was too low, i.e. the user
  under-estimated).
* absolute percentage error = |actual - estimated| / estimated. How far
  off the estimate was, regardless of direction.
* bias             = the sign of the average relative error:
                    "underestimate" (work runs longer than planned),
                    "overestimate"  (work runs shorter than planned),
                    "balanced"      (errors average out near zero).
* multiplier       = median(actual / estimated). A historical planning
                    factor: estimated * multiplier is the realistic
                    duration the user's own history implies.
"""

from dataclasses import dataclass
from datetime import date
from statistics import median


# ---------------------------------------------------------------------------
# Evidence thresholds.
#
# These are PRODUCT SAFEGUARDS, not scientifically validated thresholds.
# They exist so the app never presents a recommendation as reliable when
# only a handful of observations exist. They are intentionally conservative
# and documented here so their meaning is reviewable.
# ---------------------------------------------------------------------------

# Below this many completed observations no statistics are reported at all.
MIN_OBSERVATIONS_FOR_STATS = 3

# From this many observations the system will suggest a planning multiplier.
RECOMMENDATION_MIN_OBSERVATIONS = 10

# At or above this many observations the evidence is considered strong.
HIGH_CONFIDENCE_MIN_OBSERVATIONS = 25

# Average relative errors inside this band count as "balanced". A 5% band
# keeps day-to-day timing noise from being presented as a systematic bias.
BIAS_BAND = 0.05

# Suggested estimates are rounded to this step so they match the 5-minute
# increments used everywhere in the planner UI.
RECOMMENDATION_STEP_MINUTES = 5


@dataclass(frozen=True)
class CalibrationObservation:
    """One completed activity that produced a valid plan-vs-actual pair."""

    activity_id: int
    activity_type: str
    name: str
    estimated_minutes: int
    actual_minutes: int
    relative_error: float
    absolute_error_minutes: int
    absolute_percentage_error: float


@dataclass(frozen=True)
class CalibrationSummary:
    """All-time calibration statistics for every valid observation."""

    sample_count: int
    # Completed-but-invalid records (missing actual time, zero estimate,
    # negative duration) that could not form an observation.
    excluded_count: int
    # Activities that are not completed yet. They are not observations.
    pending_count: int
    mean_relative_error: float | None
    median_relative_error: float | None
    mean_absolute_percentage_error: float | None
    bias: str
    evidence_level: str
    # Median actual/estimated ratio; None until enough evidence exists.
    suggested_multiplier: float | None


@dataclass(frozen=True)
class CategoryCalibration:
    """Calibration statistics isolated to one activity category."""

    activity_type: str
    sample_count: int
    mean_relative_error: float | None
    mean_absolute_percentage_error: float | None
    bias: str
    evidence_level: str
    suggested_multiplier: float | None


@dataclass(frozen=True)
class CalibrationReport:
    """Complete calibration result: overall summary plus per-category."""

    summary: CalibrationSummary
    categories: tuple[CategoryCalibration, ...]
    observations: tuple[CalibrationObservation, ...]
    generated_at: str


def evidence_level_for(sample_count):
    """Map a sample count to an evidence level.

    Levels: insufficient_data / early_signal / moderate_confidence /
    high_confidence. Statistics are only meaningful from
    MIN_OBSERVATIONS_FOR_STATS; recommendations only from
    RECOMMENDATION_MIN_OBSERVATIONS.
    """
    if sample_count < MIN_OBSERVATIONS_FOR_STATS:
        return "insufficient_data"
    if sample_count < RECOMMENDATION_MIN_OBSERVATIONS:
        return "early_signal"
    if sample_count < HIGH_CONFIDENCE_MIN_OBSERVATIONS:
        return "moderate_confidence"
    return "high_confidence"


def describe_bias(mean_relative_error):
    """Return the bias label for a mean relative error, or None."""
    if mean_relative_error is None:
        return "unknown"
    if abs(mean_relative_error) < BIAS_BAND:
        return "balanced"
    if mean_relative_error > 0:
        return "underestimate"
    return "overestimate"


def make_observations(records):
    """Convert raw database records into valid calibration observations.

    Records that cannot form a trustworthy plan-vs-actual pair are skipped
    and never replaced with invented values:

    * incomplete activities (not completed) are not observations;
    * zero or negative estimates cannot produce a relative error;
    * zero or negative actual durations mean no work was recorded.
    """
    observations = []

    for record in records:
        if not record.get("completed"):
            continue

        # Compare the ORIGINAL planning estimate against the result. The
        # editable estimate may have been changed after work started; the
        # original is preserved separately by the database layer. Records
        # that predate the original-estimate column fall back to the
        # current estimate, which is the best value available for them.
        estimated = int(
            record.get("original_estimate_minutes")
            or record.get("estimated_minutes")
            or 0
        )
        actual = int(record.get("actual_minutes") or 0)

        if estimated <= 0 or actual <= 0:
            continue

        relative_error = (actual - estimated) / estimated
        observations.append(
            CalibrationObservation(
                activity_id=int(record.get("activity_id") or 0),
                activity_type=record.get("activity_type") or "Uncategorised",
                name=record.get("name") or "",
                estimated_minutes=estimated,
                actual_minutes=actual,
                relative_error=relative_error,
                absolute_error_minutes=actual - estimated,
                absolute_percentage_error=abs(relative_error),
            )
        )

    return observations


def summarize_observations(observations):
    """Compute the overall calibration summary for a list of observations."""
    sample_count = len(observations)

    if sample_count == 0:
        return CalibrationSummary(
            sample_count=0,
            excluded_count=0,
            pending_count=0,
            mean_relative_error=None,
            median_relative_error=None,
            mean_absolute_percentage_error=None,
            bias="unknown",
            evidence_level=evidence_level_for(0),
            suggested_multiplier=None,
        )

    relative_errors = [obs.relative_error for obs in observations]
    mean_relative_error = sum(relative_errors) / sample_count
    mean_absolute_percentage_error = (
        sum(obs.absolute_percentage_error for obs in observations)
        / sample_count
    )

    evidence_level = evidence_level_for(sample_count)
    suggested_multiplier = None
    if sample_count >= RECOMMENDATION_MIN_OBSERVATIONS:
        ratios = [
            obs.actual_minutes / obs.estimated_minutes
            for obs in observations
        ]
        suggested_multiplier = round(median(ratios), 2)

    return CalibrationSummary(
        sample_count=sample_count,
        excluded_count=0,
        pending_count=0,
        mean_relative_error=round(mean_relative_error, 4),
        median_relative_error=round(median(relative_errors), 4),
        mean_absolute_percentage_error=round(
            mean_absolute_percentage_error, 4
        ),
        bias=describe_bias(mean_relative_error),
        evidence_level=evidence_level,
        suggested_multiplier=suggested_multiplier,
    )


def summarize_categories(observations):
    """Compute isolated per-category calibration statistics.

    Categories are returned in a deterministic order: most observations
    first, then alphabetically.
    """
    by_category = {}
    for observation in observations:
        by_category.setdefault(observation.activity_type, []).append(
            observation
        )

    categories = []
    for activity_type, category_observations in by_category.items():
        sample_count = len(category_observations)
        relative_errors = [
            obs.relative_error for obs in category_observations
        ]
        mean_relative_error = sum(relative_errors) / sample_count
        mean_absolute_percentage_error = (
            sum(obs.absolute_percentage_error for obs in category_observations)
            / sample_count
        )

        suggested_multiplier = None
        if sample_count >= RECOMMENDATION_MIN_OBSERVATIONS:
            ratios = [
                obs.actual_minutes / obs.estimated_minutes
                for obs in category_observations
            ]
            suggested_multiplier = round(median(ratios), 2)

        categories.append(
            CategoryCalibration(
                activity_type=activity_type,
                sample_count=sample_count,
                mean_relative_error=round(mean_relative_error, 4),
                mean_absolute_percentage_error=round(
                    mean_absolute_percentage_error, 4
                ),
                bias=describe_bias(mean_relative_error),
                evidence_level=evidence_level_for(sample_count),
                suggested_multiplier=suggested_multiplier,
            )
        )

    categories.sort(
        key=lambda category: (-category.sample_count, category.activity_type)
    )
    return categories


def recommended_estimate(estimated_minutes, multiplier):
    """Return a realistic planning estimate for a planned duration.

    Multiplies the planned duration by the user's historical multiplier and
    rounds to the 5-minute step used by the planner. Returns None when no
    reliable multiplier exists.
    """
    if multiplier is None or estimated_minutes is None:
        return None

    estimated = int(estimated_minutes)
    if estimated <= 0:
        return None

    suggested = int(round(estimated * multiplier / RECOMMENDATION_STEP_MINUTES))
    suggested *= RECOMMENDATION_STEP_MINUTES
    return max(RECOMMENDATION_STEP_MINUTES, suggested)


def build_calibration_report(records, generated_at=None):
    """Build the complete calibration report from raw database records."""
    observations = make_observations(records)

    pending_count = sum(
        1 for record in records if not record.get("completed")
    )
    excluded_count = len(records) - pending_count - len(observations)

    summary = summarize_observations(observations)
    summary = CalibrationSummary(
        sample_count=summary.sample_count,
        excluded_count=excluded_count,
        pending_count=pending_count,
        mean_relative_error=summary.mean_relative_error,
        median_relative_error=summary.median_relative_error,
        mean_absolute_percentage_error=summary.mean_absolute_percentage_error,
        bias=summary.bias,
        evidence_level=summary.evidence_level,
        suggested_multiplier=summary.suggested_multiplier,
    )

    return CalibrationReport(
        summary=summary,
        categories=tuple(summarize_categories(observations)),
        observations=tuple(observations),
        generated_at=(generated_at or date.today().isoformat()),
    )


class CalibrationService:
    """Build the all-time estimate-calibration report from persisted data.

    Calibration uses ALL completed activities, not a time window: the more
    observations exist, the more reliable the statistics are. The service
    only reads data; it never writes.
    """

    def __init__(self, database):
        self.database = database

    def build_report(self, today=None):
        """Return the calibration report for all persisted activities."""
        records = self.database.get_calibration_records()
        return build_calibration_report(
            records,
            generated_at=(today or date.today()).isoformat(),
        )


# ---------------------------------------------------------------------------
# Presentation helpers shared with the Insights UI.
# ---------------------------------------------------------------------------

EVIDENCE_LABELS = {
    "insufficient_data": "Insufficient data",
    "early_signal": "Early signal",
    "moderate_confidence": "Moderate confidence",
    "high_confidence": "High confidence",
}

BIAS_LABELS = {
    "underestimate": "underestimating",
    "overestimate": "overestimating",
    "balanced": "on target",
    "unknown": "unknown",
}


def evidence_label(evidence_level):
    """Human-readable evidence level label."""
    return EVIDENCE_LABELS.get(evidence_level, evidence_level)


def format_error_percent(fraction):
    """Format a signed relative-error fraction like the product copy does.

    +0.25 -> "+25%", -0.25 -> "-25%", 0.0 -> "0%".
    """
    percentage = round(fraction * 100)
    if percentage > 0:
        return f"+{percentage}%"
    return f"{percentage}%"


def format_plain_percent(fraction):
    """Format a magnitude percentage without a sign.

    0.3469 -> "35%". Used for absolute errors, which have no direction.
    """
    return f"{round(fraction * 100)}%"
