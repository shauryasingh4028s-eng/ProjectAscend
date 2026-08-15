"""Smart Activity Estimates: suggestion selection for the Add Activity flow.

This module turns an existing CalibrationReport into an optional,
user-facing estimate suggestion. It is deliberately a THIN consumer of the
calibration engine:

* Evidence thresholds are NOT redefined here. A multiplier exists on the
  report only when the CalibrationService decided the evidence was
  sufficient (RECOMMENDATION_MIN_OBSERVATIONS), so this module simply
  checks whether a multiplier is present.
* The recommendation arithmetic is NOT reimplemented here. The suggested
  duration always comes from the existing recommended_estimate() helper.

Presentation rules owned by this module (product decisions, not
statistics):

* Category first: a reliable multiplier for the selected activity type is
  preferred over the overall multiplier, because it is the most specific
  honest evidence available.
* Identity suppression: a suggestion equal to the value the user already
  entered is noise and is never shown.
* Range honesty: a recommendation outside the dialog's valid input range
  is HIDDEN, never clamped. Clamping (e.g. presenting an engine result of
  720 min as 600 min) would misrepresent what Ascend actually recommends.
* Time-first copy: the actionable text speaks in minutes, never in
  percentages.

The module is Qt-free so the decision logic is fully testable without a
GUI environment.
"""

from dataclasses import dataclass

from Modules.calibration_service import recommended_estimate


@dataclass(frozen=True)
class EstimateSuggestion:
    """One displayable suggestion, anchored to the user's own estimate."""

    entered_minutes: int
    suggested_minutes: int
    difference_minutes: int
    sample_count: int
    # "category" when the selected activity type had reliable evidence of
    # its own, "overall" when the all-categories multiplier was used.
    source: str
    # The category the evidence came from; None for overall evidence.
    activity_type: str | None
    headline: str
    difference_text: str
    evidence_text: str
    keep_label: str
    use_label: str


def select_evidence(report, activity_type):
    """Pick the most specific reliable multiplier from a calibration report.

    Returns (multiplier, sample_count, source, activity_type_or_None) or
    None when no reliable evidence exists anywhere.

    Reliability is delegated entirely to the CalibrationService: a
    multiplier is only present on the report when the service's own
    RECOMMENDATION_MIN_OBSERVATIONS threshold was met. No threshold is
    duplicated or weakened here.
    """
    if report is None:
        return None

    for category in report.categories:
        if (
            category.activity_type == activity_type
            and category.suggested_multiplier is not None
        ):
            return (
                category.suggested_multiplier,
                category.sample_count,
                "category",
                category.activity_type,
            )

    summary = report.summary
    if summary.suggested_multiplier is not None:
        return (
            summary.suggested_multiplier,
            summary.sample_count,
            "overall",
            None,
        )

    return None


def build_difference_text(difference_minutes):
    """Time-first supporting copy: the difference in concrete minutes."""
    if difference_minutes > 0:
        return f"About {difference_minutes} min more than your estimate."
    return f"About {-difference_minutes} min less than your estimate."


def build_evidence_text(sample_count, source, activity_type):
    """Honest supporting copy stating exactly what the evidence is."""
    if source == "category":
        return (
            f"Based on {sample_count} completed "
            f"{activity_type} activities."
        )
    return f"Based on {sample_count} completed activities."


def suggest_estimate(
    report,
    activity_type,
    entered_minutes,
    minimum_minutes,
    maximum_minutes,
):
    """Return an EstimateSuggestion for the user's entered duration, or None.

    None means "show nothing": insufficient evidence, a suggestion equal
    to the entered value, or an engine recommendation outside the valid
    input range. The caller never needs to explain an absent suggestion -
    the normal dialog experience simply remains clean.
    """
    entered = int(entered_minutes)

    evidence = select_evidence(report, activity_type)
    if evidence is None:
        return None
    multiplier, sample_count, source, evidence_type = evidence

    # The one and only place the recommendation is calculated: the
    # existing calibration helper. Its arithmetic is never reproduced.
    suggested = recommended_estimate(entered, multiplier)
    if suggested is None:
        return None

    # Identity suppression: recommending the value the user already typed
    # is noise, not intelligence.
    if suggested == entered:
        return None

    # Range honesty: a recommendation the dialog cannot actually hold is
    # hidden rather than silently altered.
    if suggested < minimum_minutes or suggested > maximum_minutes:
        return None

    difference = suggested - entered

    return EstimateSuggestion(
        entered_minutes=entered,
        suggested_minutes=suggested,
        difference_minutes=difference,
        sample_count=sample_count,
        source=source,
        activity_type=evidence_type,
        headline=f"Ascend suggests ~{suggested} min",
        difference_text=build_difference_text(difference),
        evidence_text=build_evidence_text(
            sample_count, source, evidence_type
        ),
        keep_label=f"Keep {entered} min",
        use_label=f"Use {suggested} min",
    )
