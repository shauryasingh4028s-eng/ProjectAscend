"""Smart Activity Estimates: personalized suggestions for Add Activity.

This is the additive Smart Estimate intelligence layer. It consumes the
same historical records as the calibration engine but learns a different,
more human statistic: the user's typical ABSOLUTE time difference

    median(actual_minutes - original_estimate_minutes)

per evidence tier, instead of the engine's proportional multiplier. The
multiplier model remains the property of CalibrationService and continues
to power Planning Accuracy and Insights untouched.

Evidence hierarchy (first reliable tier wins; tiers are never blended):

    Exact activity  - same category AND same normalized name
        v
    Category        - same activity_type
        v
    Overall         - all valid observations
        v
    No recommendation

Product safeguards owned by this layer:

* Observation validity is single-sourced: records become observations
  through the calibration engine's own make_observations(), so
  "completed, original estimate > 0, actual > 0" is never redefined.
  Because observations compare against the ORIGINAL planning estimate
  (frozen by the database once work is recorded), an accepted suggestion
  can never become the estimate the model later learns from - no
  feedback loop.
* Conservative thresholds. Exact-activity evidence is the least
  heterogeneous data the system has, so it unlocks at 5 observations;
  category and overall tiers keep the calibration engine's own
  recommendation bar of 10.
* Relevance window. A tier's learned bias only applies when the entered
  estimate is inside the range of that tier's OBSERVED original
  estimates (extended by one 5-minute step). Outside it, the tier is
  treated as unavailable for this input: the model refuses to
  extrapolate rather than guessing.
* Identity suppression: a suggestion equal to the entered value is
  noise and is hidden.
* Range honesty: a recommendation outside the dialog's valid input
  range is HIDDEN, never clamped, so the engine's number is never
  misrepresented.
* Time-first copy: concrete minutes, never percentages or multipliers.

Activity identity is deliberately strict: exact match on
(activity_type, normalized name), where normalization only trims,
collapses internal whitespace and ignores case. "Maths Test 2",
"Maths Test - Chapter 5" and "Maths Test (Final)" are different
activities from "Maths Test"; falsely merging them would fabricate
exact-activity evidence. No fuzzy matching of any kind.

The module is Qt-free so the decision logic is fully testable without a
GUI environment.
"""

from dataclasses import dataclass
from statistics import median

from Modules.calibration_service import (
    RECOMMENDATION_MIN_OBSERVATIONS,
    RECOMMENDATION_STEP_MINUTES,
    make_observations,
)


# ---------------------------------------------------------------------------
# Evidence thresholds for the Smart Estimate layer.
#
# PRODUCT SAFEGUARDS, in the same spirit as the calibration engine's own
# documented thresholds. Category and overall reuse the engine's
# recommendation bar directly (single-sourced, not a copied literal).
# Exact-activity evidence is repeats of ONE specific activity - far lower
# variance per observation - so it unlocks earlier, but still requires a
# genuinely established pattern.
# ---------------------------------------------------------------------------

EXACT_MIN_OBSERVATIONS = 5
CATEGORY_MIN_OBSERVATIONS = RECOMMENDATION_MIN_OBSERVATIONS
OVERALL_MIN_OBSERVATIONS = RECOMMENDATION_MIN_OBSERVATIONS

# The relevance window around a tier's observed original estimates is
# extended by one planner step on each side.
RELEVANCE_MARGIN_MINUTES = RECOMMENDATION_STEP_MINUTES


@dataclass(frozen=True)
class EstimateSuggestion:
    """One displayable suggestion, anchored to the user's own estimate."""

    entered_minutes: int
    suggested_minutes: int
    # Displayed difference, derived from the FINAL ROUNDED suggestion so
    # the two numbers shown to the user are always consistent.
    difference_minutes: int
    # The raw learned statistic (median of actual - original), kept for
    # transparency and tests; never shown directly.
    median_bias_minutes: float
    sample_count: int
    # "exact" | "category" | "overall"
    source: str
    # The category the evidence came from ("exact"/"category"), or None.
    activity_type: str | None
    # The historical activity name the exact tier matched, or None.
    activity_name: str | None
    headline: str
    difference_text: str
    evidence_text: str
    keep_label: str
    use_label: str


def normalize_name(name):
    """Conservative activity-name identity: trim, collapse internal
    whitespace, ignore case. Nothing else - two names normalize equal
    only when no user would consider them different activities."""
    return " ".join((name or "").split()).casefold()


def observation_bias(observations):
    """The learned time bias for a group: median(actual - estimated).

    The median is robust to outliers by construction (one derailed
    session cannot move it) and matches the engine's established
    robust-center choice. No trimming is layered on top.
    """
    return median(
        obs.actual_minutes - obs.estimated_minutes
        for obs in observations
    )


def is_relevant(observations, entered_minutes):
    """Relevance window: only apply a tier's bias when the entered
    estimate is inside the range of that tier's observed ORIGINAL
    estimates, extended by one planner step. Outside it the tier has no
    evidence for this input and must not extrapolate."""
    observed = [obs.estimated_minutes for obs in observations]
    lower = min(observed) - RELEVANCE_MARGIN_MINUTES
    upper = max(observed) + RELEVANCE_MARGIN_MINUTES
    return lower <= entered_minutes <= upper


def select_evidence(observations, activity_type, activity_name,
                    entered_minutes):
    """Pick the most specific reliable evidence tier for this input.

    Returns (tier_observations, source, activity_type, matched_name) or
    None when no tier is both sufficiently evidenced and relevant to the
    entered estimate. The first reliable tier wins; tiers are never
    blended.
    """
    normalized = normalize_name(activity_name)

    # Tier 1 - exact activity: same category AND same normalized name.
    # A blank name never forms an exact-activity group.
    if normalized:
        exact = [
            obs for obs in observations
            if obs.activity_type == activity_type
            and normalize_name(obs.name) == normalized
        ]
        if (
            len(exact) >= EXACT_MIN_OBSERVATIONS
            and is_relevant(exact, entered_minutes)
        ):
            return exact, "exact", activity_type, activity_name.strip()

    # Tier 2 - category.
    category = [
        obs for obs in observations
        if obs.activity_type == activity_type
    ]
    if (
        len(category) >= CATEGORY_MIN_OBSERVATIONS
        and is_relevant(category, entered_minutes)
    ):
        return category, "category", activity_type, None

    # Tier 3 - overall personal history.
    if (
        len(observations) >= OVERALL_MIN_OBSERVATIONS
        and is_relevant(observations, entered_minutes)
    ):
        return observations, "overall", None, None

    return None


def round_to_step(minutes):
    """Round to the 5-minute planner step used everywhere in the UI."""
    steps = int(round(minutes / RECOMMENDATION_STEP_MINUTES))
    return steps * RECOMMENDATION_STEP_MINUTES


def build_difference_text(difference_minutes):
    """Time-first copy describing the user's learned behaviour."""
    if difference_minutes > 0:
        return f"You typically take ~{difference_minutes} min longer."
    return f"You typically finish ~{-difference_minutes} min early."


def build_evidence_text(sample_count, source, activity_type,
                        activity_name):
    """Honest supporting copy naming exactly which evidence was used."""
    if source == "exact":
        return (
            f'Based on {sample_count} previous '
            f'"{activity_name}" sessions.'
        )
    if source == "category":
        return (
            f"Based on {sample_count} previous "
            f"{activity_type} activities."
        )
    return f"Based on {sample_count} completed activities."


def suggest_estimate(
    records,
    activity_type,
    activity_name,
    entered_minutes,
    minimum_minutes,
    maximum_minutes,
):
    """Return an EstimateSuggestion for the user's entered duration, or None.

    `records` are raw rows from Database.get_calibration_records(); they
    become observations through the calibration engine's own
    make_observations(), so validity rules stay single-sourced.

    None means "show nothing": insufficient evidence at every tier, an
    entered estimate outside every tier's relevance window, a suggestion
    that rounds back to the entered value, or a recommendation outside
    the valid input range. The caller never needs to explain an absent
    suggestion - the normal dialog experience simply remains clean.
    """
    entered = int(entered_minutes)

    observations = make_observations(records or [])

    evidence = select_evidence(
        observations, activity_type, activity_name, entered
    )
    if evidence is None:
        return None
    tier_observations, source, evidence_type, matched_name = evidence

    bias = observation_bias(tier_observations)

    # The recommendation: the user's own anchor plus their learned
    # typical difference, rounded to the planner step.
    suggested = round_to_step(entered + bias)

    # Identity suppression: recommending the value the user already
    # typed is noise, not intelligence.
    if suggested == entered:
        return None

    # Range honesty: a recommendation the dialog cannot actually hold is
    # hidden rather than silently altered.
    if suggested < minimum_minutes or suggested > maximum_minutes:
        return None

    # The displayed delta is derived from the FINAL rounded suggestion,
    # never from the raw bias, so the card is internally consistent.
    difference = suggested - entered

    return EstimateSuggestion(
        entered_minutes=entered,
        suggested_minutes=suggested,
        difference_minutes=difference,
        median_bias_minutes=float(bias),
        sample_count=len(tier_observations),
        source=source,
        activity_type=evidence_type,
        activity_name=matched_name,
        headline=f"Ascend suggests ~{suggested} min",
        difference_text=build_difference_text(difference),
        evidence_text=build_evidence_text(
            len(tier_observations), source, evidence_type, matched_name
        ),
        keep_label=f"Keep {entered} min",
        use_label=f"Use {suggested} min",
    )
