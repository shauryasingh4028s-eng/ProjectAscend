"""Persisted-data analytics and insight generation for Project Ascend."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, pstdev

from Modules.calibration_service import (
    BIAS_BAND,
    RECOMMENDATION_MIN_OBSERVATIONS,
    CalibrationReport,
    CalibrationService,
    format_error_percent,
    format_plain_percent,
)
from Modules.date_utils import format_display_date


@dataclass(frozen=True)
class RangeDefinition:
    key: str
    label: str
    start_date: date
    end_date: date
    # ``None`` when there is no comparable previous period (All Time).
    previous_start_date: date | None
    previous_end_date: date | None


@dataclass(frozen=True)
class DailyFocus:
    day: date
    focus_minutes: int
    completed_tasks: int
    total_tasks: int


@dataclass(frozen=True)
class OverviewData:
    focus_minutes: int
    completed_tasks: int
    total_tasks: int
    completion_rate: int
    current_streak: int
    xp_earned: int | None
    xp_status: str | None
    # Comparison with the previous equivalent period. Every delta is None
    # when no comparable previous data exists - the UI never invents one.
    previous_focus_minutes: int = 0
    focus_change_percent: int | None = None
    previous_completion_rate: int | None = None
    completion_change_points: int | None = None
    previous_completed_tasks: int = 0
    activity_change: int | None = None
    active_days: int = 0


@dataclass(frozen=True)
class TrendComparison:
    text: str
    direction: str
    percentage: int | None
    previous_focus_minutes: int


@dataclass(frozen=True)
class FocusTrendData:
    points: tuple[DailyFocus, ...]
    total_focus_minutes: int
    daily_average_minutes: int
    comparison: TrendComparison
    # How the points are bucketed: "daily", "weekly" or "monthly". Long
    # ranges are aggregated so the chart stays readable.
    granularity: str = "daily"


@dataclass(frozen=True)
class ProductivityPatterns:
    best_day_name: str | None
    best_day_focus_minutes: int
    best_time_label: str | None
    best_time_focus_minutes: int
    best_category_name: str | None
    best_category_focus_minutes: int
    active_days: int
    period_days: int


@dataclass(frozen=True)
class HeatmapDay:
    day: date
    focus_minutes: int
    level: str


@dataclass(frozen=True)
class ConsistencyData:
    heatmap_days: tuple[HeatmapDay, ...]
    current_streak: int
    best_streak: int
    active_days: int
    period_days: int
    goal_success_days: int
    daily_goal_minutes: int

    @property
    def goal_success_rate(self):
        if self.period_days == 0:
            return 0
        return round((self.goal_success_days / self.period_days) * 100)


@dataclass(frozen=True)
class ActivityShare:
    category: str
    focus_minutes: int
    percent: int


@dataclass(frozen=True)
class ActivityDistribution:
    items: tuple[ActivityShare, ...]
    total_minutes: int


@dataclass(frozen=True)
class DayHourCell:
    day_index: int  # 0 = Monday ... 6 = Sunday
    block_index: int  # 0 = Morning, 1 = Afternoon, 2 = Evening, 3 = Night
    focus_minutes: int
    session_count: int


@dataclass(frozen=True)
class DayHourPattern:
    """Where the user's focused work lands across the week."""

    cells: tuple[DayHourCell, ...]
    total_sessions: int
    total_minutes: int
    strongest_window_label: str | None
    strongest_window_minutes: int
    window_session_count: int
    # "empty" (no sessions), "learning" (too few sessions), "ready".
    status: str


@dataclass(frozen=True)
class Highlight:
    title: str
    value: str
    note: str


@dataclass(frozen=True)
class HighlightsData:
    best_day: Highlight | None
    longest_session: Highlight | None
    improvement: Highlight | None


@dataclass(frozen=True)
class LearnedInsight:
    """One evidence-backed observation about the user's behaviour.

    Confidence uses the same vocabulary as calibration evidence levels:
    early_signal / moderate_confidence / high_confidence. Insights are only
    produced when the underlying evidence thresholds are met; they are
    never invented from weak signals.
    """

    title: str
    description: str
    evidence: str
    confidence: str


@dataclass(frozen=True)
class InsightItem:
    kind: str
    title: str
    description: str
    metric: str | None = None


@dataclass(frozen=True)
class InsightsDashboardData:
    range_definition: RangeDefinition
    overview: OverviewData
    trend: FocusTrendData
    patterns: ProductivityPatterns
    consistency: ConsistencyData
    # All-time estimate calibration. This is deliberately independent of the
    # selected range: calibration needs every completed observation there is.
    calibration: CalibrationReport
    distribution: ActivityDistribution
    day_hour: DayHourPattern
    highlights: HighlightsData
    learned: tuple[LearnedInsight, ...]
    insights: tuple[InsightItem, ...]


class InsightsService:
    """Build one complete Insights view model from a persisted data snapshot."""

    RANGE_DAYS = {
        "today": 1,
        "7_days": 7,
        "30_days": 30,
        "90_days": 90,
        "all_time": None,
    }

    RANGE_LABELS = {
        "today": "Today",
        "7_days": "7 Days",
        "30_days": "30 Days",
        "90_days": "3 Months",
        "all_time": "All Time",
    }

    COMPARISON_LABELS = {
        "today": "previous day",
        "7_days": "previous week",
        "30_days": "previous 30 days",
        "90_days": "previous 3 months",
        "all_time": "previous period",
    }

    # ------------------------------------------------------------------
    # Time-of-day blocks used by the "When You Work Best" heatmap.
    # ------------------------------------------------------------------
    TIME_BLOCKS = (
        (5, 12, "Morning"),
        (12, 17, "Afternoon"),
        (17, 22, "Evening"),
        (22, 29, "Night"),  # 22:00 - 05:00
    )

    # ------------------------------------------------------------------
    # Evidence thresholds for "What Ascend Learned".
    #
    # These are product safeguards, not scientific claims: an observation
    # only becomes an insight when enough real data exists. Thresholds are
    # deliberately conservative and documented here for review.
    # ------------------------------------------------------------------
    RHYTHM_MIN_SESSIONS = 8
    WINDOW_MIN_SESSIONS = 3
    RHYTHM_HIGH_SHARE = 0.4  # window share of all focus for high confidence
    CATEGORY_INSIGHT_MIN_SAMPLES = 5
    CATEGORY_INSIGHT_MIN_ERROR = 0.10
    DAY_INSIGHT_MIN_ACTIVE_DAYS = 3
    DAY_INSIGHT_MIN_MINUTES = 60
    CONSISTENCY_IMPROVEMENT_MIN_ACTIVE_HALF = 3
    CONSISTENCY_IMPROVEMENT_RATIO = 0.8  # newer variability / older
    PLANNING_TREND_MIN_SAMPLES = 8
    PLANNING_TREND_IMPROVEMENT_RATIO = 0.85  # newer error / older

    # Ranked time-distribution bars shown before merging into "Other".
    DISTRIBUTION_MAX_ITEMS = 6

    def __init__(self, database, streak_manager):
        self.database = database
        self.streak_manager = streak_manager
        self.calibration_service = CalibrationService(database)

    def build_dashboard(self, range_key="7_days", today=None):
        """Return all analytics needed to render one selected Insights range."""
        range_definition = self.get_range_definition(range_key, today)
        fetch_start = (
            range_definition.previous_start_date
            or range_definition.start_date
        )
        records = self.database.get_insights_records(
            fetch_start.isoformat(),
            range_definition.end_date.isoformat(),
        )
        current_activities, previous_activities = self.partition_records(
            records["activities"],
            "date",
            range_definition,
        )
        current_sessions, _ = self.partition_records(
            records["focus_sessions"],
            "session_date",
            range_definition,
        )
        current_xp_events, _ = self.partition_records(
            records["xp_events"],
            "earned_date",
            range_definition,
        )

        current_days = self.build_daily_focus(
            current_activities,
            range_definition.start_date,
            range_definition.end_date,
        )
        previous_days = self.build_daily_focus(
            previous_activities,
            range_definition.previous_start_date,
            range_definition.previous_end_date,
        ) if range_definition.previous_start_date is not None else []
        current_focus = sum(item.focus_minutes for item in current_days)
        previous_focus = sum(item.focus_minutes for item in previous_days)
        completed_tasks = sum(item.completed_tasks for item in current_days)
        total_tasks = sum(item.total_tasks for item in current_days)
        previous_completed_tasks = sum(
            item.completed_tasks for item in previous_days
        )
        previous_total_tasks = sum(
            item.total_tasks for item in previous_days
        )
        current_streak = self.streak_manager.get_current_streak()
        best_streak = self.streak_manager.get_longest_streak()
        xp_earned, xp_status = self.calculate_xp_earned(
            current_xp_events,
        )

        patterns = self.build_patterns(
            current_days,
            current_activities,
            current_sessions,
        )
        comparison = self.build_comparison(
            current_focus,
            previous_focus,
            range_definition,
        )

        has_previous_data = (
            previous_total_tasks > 0 or previous_focus > 0
        )
        previous_completion_rate = self.calculate_percentage(
            previous_completed_tasks,
            previous_total_tasks,
        ) if has_previous_data else None
        completion_rate = self.calculate_percentage(
            completed_tasks,
            total_tasks,
        )

        overview = OverviewData(
            focus_minutes=current_focus,
            completed_tasks=completed_tasks,
            total_tasks=total_tasks,
            completion_rate=completion_rate,
            current_streak=current_streak,
            xp_earned=xp_earned,
            xp_status=xp_status,
            previous_focus_minutes=previous_focus,
            focus_change_percent=comparison.percentage,
            previous_completion_rate=previous_completion_rate,
            completion_change_points=(
                completion_rate - previous_completion_rate
                if previous_completion_rate is not None
                else None
            ),
            previous_completed_tasks=previous_completed_tasks,
            activity_change=(
                completed_tasks - previous_completed_tasks
                if has_previous_data
                else None
            ),
            active_days=patterns.active_days,
        )
        trend_points, granularity = self.build_trend_points(
            current_days,
            range_key,
        )
        trend = FocusTrendData(
            points=tuple(trend_points),
            total_focus_minutes=current_focus,
            daily_average_minutes=round(
                current_focus / len(current_days)
            ) if current_days else 0,
            comparison=comparison,
            granularity=granularity,
        )
        consistency = self.build_consistency(
            current_days,
            records["daily_goal_minutes"],
            current_streak,
            best_streak,
        )
        calibration = self.calibration_service.build_report(today)
        distribution = self.build_distribution(current_activities)
        day_hour = self.build_day_hour_pattern(current_sessions)
        highlights = self.build_highlights(
            patterns,
            comparison,
            current_sessions,
            range_definition,
        )
        learned = self.build_learned_insights(
            day_hour,
            patterns,
            consistency,
            calibration,
            current_days,
        )

        insights = self.generate_insights(
            overview,
            trend,
            patterns,
            consistency,
            calibration,
        )

        return InsightsDashboardData(
            range_definition=range_definition,
            overview=overview,
            trend=trend,
            patterns=patterns,
            consistency=consistency,
            calibration=calibration,
            distribution=distribution,
            day_hour=day_hour,
            highlights=highlights,
            learned=tuple(learned),
            insights=tuple(insights),
        )

    def get_range_definition(self, range_key, today=None):
        if range_key not in self.RANGE_DAYS:
            range_key = "7_days"

        end_date = today or date.today()
        period_days = self.RANGE_DAYS[range_key]

        if range_key == "all_time":
            # The range starts at the user's earliest recorded data, so the
            # chart never shows a long tail of empty days. There is no
            # previous equivalent period to compare against.
            earliest = self.database.get_earliest_record_date()
            start_date = (
                self.parse_record_date(earliest) or end_date
            )
            return RangeDefinition(
                key=range_key,
                label=self.RANGE_LABELS[range_key],
                start_date=start_date,
                end_date=end_date,
                previous_start_date=None,
                previous_end_date=None,
            )

        start_date = end_date - timedelta(days=period_days - 1)
        previous_end_date = start_date - timedelta(days=1)
        previous_start_date = previous_end_date - timedelta(
            days=period_days - 1
        )
        return RangeDefinition(
            key=range_key,
            label=self.RANGE_LABELS[range_key],
            start_date=start_date,
            end_date=end_date,
            previous_start_date=previous_start_date,
            previous_end_date=previous_end_date,
        )

    def partition_records(self, records, date_key, range_definition):
        current_records = []
        previous_records = []
        previous_start = range_definition.previous_start_date
        previous_end = range_definition.previous_end_date
        for record in records:
            record_date = self.parse_record_date(record.get(date_key))
            if record_date is None:
                continue
            if range_definition.start_date <= record_date <= range_definition.end_date:
                current_records.append(record)
            elif (
                previous_start is not None
                and previous_end is not None
                and previous_start <= record_date <= previous_end
            ):
                previous_records.append(record)
        return current_records, previous_records

    def build_daily_focus(self, activities, start_date, end_date):
        totals = {}
        current_day = start_date
        while current_day <= end_date:
            totals[current_day] = {
                "focus_minutes": 0,
                "completed_tasks": 0,
                "total_tasks": 0,
            }
            current_day += timedelta(days=1)

        for activity in activities:
            activity_date = self.parse_record_date(activity.get("date"))
            if activity_date not in totals:
                continue
            day_totals = totals[activity_date]
            day_totals["total_tasks"] += 1
            if activity.get("completed"):
                day_totals["completed_tasks"] += 1
                day_totals["focus_minutes"] += max(
                    0,
                    int(activity.get("actual_minutes") or 0),
                )

        return [
            DailyFocus(
                day=day,
                focus_minutes=values["focus_minutes"],
                completed_tasks=values["completed_tasks"],
                total_tasks=values["total_tasks"],
            )
            for day, values in totals.items()
        ]

    def build_comparison(self, current_minutes, previous_minutes, range_definition):
        period_label = self.COMPARISON_LABELS.get(
            range_definition.key,
            "previous period",
        )

        if previous_minutes == 0:
            if current_minutes == 0:
                return TrendComparison(
                    text="No previous data",
                    direction="neutral",
                    percentage=None,
                    previous_focus_minutes=0,
                )
            return TrendComparison(
                text="New baseline",
                direction="positive",
                percentage=None,
                previous_focus_minutes=0,
            )

        change = round(((current_minutes - previous_minutes) / previous_minutes) * 100)
        if change > 0:
            text = f"{change}% more than {period_label}"
            direction = "positive"
        elif change < 0:
            text = f"{abs(change)}% less than {period_label}"
            direction = "negative"
        else:
            text = f"Same as {period_label}"
            direction = "neutral"
        return TrendComparison(
            text=text,
            direction=direction,
            percentage=change,
            previous_focus_minutes=previous_minutes,
        )

    def build_patterns(self, daily_focus, activities, sessions):
        focus_by_weekday = {}
        for daily in daily_focus:
            if daily.focus_minutes <= 0:
                continue
            weekday = daily.day.strftime("%A")
            focus_by_weekday[weekday] = (
                focus_by_weekday.get(weekday, 0) + daily.focus_minutes
            )

        if focus_by_weekday:
            best_day_name, best_day_minutes = min(
                focus_by_weekday.items(),
                key=lambda item: (-item[1], item[0]),
            )
        else:
            best_day_name, best_day_minutes = None, 0

        focus_by_hour_block = {}
        for session in sessions:
            minutes = max(0, int(session.get("actual_minutes") or 0))
            started_at = self.parse_timestamp(session.get("started_at"))
            if started_at is None or minutes <= 0:
                continue
            block_start = (started_at.hour // 2) * 2
            focus_by_hour_block[block_start] = (
                focus_by_hour_block.get(block_start, 0) + minutes
            )

        if focus_by_hour_block:
            best_hour, best_time_minutes = min(
                focus_by_hour_block.items(),
                key=lambda item: (-item[1], item[0]),
            )
            best_time_label = self.format_hour_block(best_hour)
        else:
            best_time_label, best_time_minutes = None, 0

        focus_by_category = {}
        for activity in activities:
            if not activity.get("completed"):
                continue
            minutes = max(0, int(activity.get("actual_minutes") or 0))
            if minutes <= 0:
                continue
            category = activity.get("activity_type") or "Uncategorised"
            focus_by_category[category] = (
                focus_by_category.get(category, 0) + minutes
            )

        if focus_by_category:
            best_category_name, best_category_minutes = min(
                focus_by_category.items(),
                key=lambda item: (-item[1], item[0]),
            )
        else:
            best_category_name, best_category_minutes = None, 0

        active_days = sum(
            1
            for daily in daily_focus
            if daily.focus_minutes > 0 or daily.completed_tasks > 0
        )
        return ProductivityPatterns(
            best_day_name=best_day_name,
            best_day_focus_minutes=best_day_minutes,
            best_time_label=best_time_label,
            best_time_focus_minutes=best_time_minutes,
            best_category_name=best_category_name,
            best_category_focus_minutes=best_category_minutes,
            active_days=active_days,
            period_days=len(daily_focus),
        )

    def build_trend_points(self, daily_focus, range_key):
        """Aggregate daily focus points for long ranges so the chart stays
        readable. Short ranges stay daily; 90-day ranges become weekly
        buckets; longer spans become monthly buckets."""
        if not daily_focus:
            return [], "daily"

        span_days = (daily_focus[-1].day - daily_focus[0].day).days + 1
        if range_key in ("today", "7_days", "30_days") or span_days <= 31:
            return daily_focus, "daily"
        if span_days <= 180:
            return self._bucket_days(daily_focus, 7), "weekly"
        return self._bucket_days(daily_focus, 30), "monthly"

    @staticmethod
    def _bucket_days(daily_focus, bucket_size):
        """Merge consecutive days into fixed-size buckets, keeping the
        bucket's first day as its label anchor."""
        buckets = []
        for index in range(0, len(daily_focus), bucket_size):
            chunk = daily_focus[index:index + bucket_size]
            first = chunk[0]
            buckets.append(
                DailyFocus(
                    day=first.day,
                    focus_minutes=sum(
                        point.focus_minutes for point in chunk
                    ),
                    completed_tasks=sum(
                        point.completed_tasks for point in chunk
                    ),
                    total_tasks=sum(point.total_tasks for point in chunk),
                )
            )
        return buckets

    def build_distribution(self, activities, max_items=None):
        """Ranked focus-time distribution by activity category.

        Only categories that actually exist are shown. When there are more
        categories than fit, the remainder is honestly merged into one
        "Other" bar - no invented categories, no fabricated minutes.
        """
        max_items = max_items or self.DISTRIBUTION_MAX_ITEMS
        focus_by_category = {}
        for activity in activities:
            if not activity.get("completed"):
                continue
            minutes = max(0, int(activity.get("actual_minutes") or 0))
            if minutes <= 0:
                continue
            category = activity.get("activity_type") or "Uncategorised"
            focus_by_category[category] = (
                focus_by_category.get(category, 0) + minutes
            )

        if not focus_by_category:
            return ActivityDistribution(items=(), total_minutes=0)

        ordered = sorted(
            focus_by_category.items(),
            key=lambda item: (-item[1], item[0]),
        )
        total = sum(minutes for _, minutes in ordered)
        visible = ordered[:max_items]

        items = []
        for category, minutes in visible:
            items.append(
                ActivityShare(
                    category=category,
                    focus_minutes=minutes,
                    percent=round((minutes / total) * 100),
                )
            )

        if len(ordered) > max_items:
            other_minutes = sum(
                minutes for _, minutes in ordered[max_items:]
            )
            items.append(
                ActivityShare(
                    category="Other",
                    focus_minutes=other_minutes,
                    percent=0,
                )
            )

        # Make the percentages add up to exactly 100 by adjusting the last
        # bar, so the visual always reconciles with the total.
        if items:
            items[-1] = ActivityShare(
                category=items[-1].category,
                focus_minutes=items[-1].focus_minutes,
                percent=max(0, 100 - sum(item.percent for item in items[:-1])),
            )

        return ActivityDistribution(items=tuple(items), total_minutes=total)

    @staticmethod
    def block_index_for_hour(hour):
        """Map an hour to a time-of-day block index (0-3)."""
        if 5 <= hour < 12:
            return 0
        if 12 <= hour < 17:
            return 1
        if 17 <= hour < 22:
            return 2
        return 3

    def build_day_hour_pattern(self, sessions):
        """Build the day-of-week x time-of-day focus heatmap data.

        The strongest 2-hour focus window is derived from timestamped
        sessions. A window is only claimed when enough sessions exist;
        otherwise the status stays "learning" and the UI says so.
        """
        cells = {}
        total_minutes = 0
        total_sessions = 0
        window_minutes = {}
        window_counts = {}

        for session in sessions:
            minutes = max(0, int(session.get("actual_minutes") or 0))
            started_at = self.parse_timestamp(session.get("started_at"))
            if started_at is None or minutes <= 0:
                continue

            total_sessions += 1
            total_minutes += minutes

            day_index = started_at.weekday()
            block_index = self.block_index_for_hour(started_at.hour)
            key = (day_index, block_index)
            cell_minutes, cell_count = cells.get(key, (0, 0))
            cells[key] = (cell_minutes + minutes, cell_count + 1)

            # 2-hour sliding windows: a session counts toward every window
            # that contains its start hour.
            hour = started_at.hour
            for window_start in range(24):
                if (hour - window_start) % 24 < 2:
                    window_minutes[window_start] = (
                        window_minutes.get(window_start, 0) + minutes
                    )
                    window_counts[window_start] = (
                        window_counts.get(window_start, 0) + 1
                    )

        cell_list = [
            DayHourCell(
                day_index=day_index,
                block_index=block_index,
                focus_minutes=minutes,
                session_count=count,
            )
            for (day_index, block_index), (minutes, count) in sorted(
                cells.items()
            )
        ]

        if window_minutes:
            strongest_hour = max(
                window_minutes,
                key=lambda hour: (window_minutes[hour], -hour),
            )
            strongest_window_label = self.format_hour_block(strongest_hour)
            strongest_window_minutes = window_minutes[strongest_hour]
            window_session_count = window_counts[strongest_hour]
        else:
            strongest_window_label = None
            strongest_window_minutes = 0
            window_session_count = 0

        if total_sessions == 0:
            status = "empty"
        elif (
            total_sessions >= self.RHYTHM_MIN_SESSIONS
            and window_session_count >= self.WINDOW_MIN_SESSIONS
        ):
            status = "ready"
        else:
            status = "learning"

        return DayHourPattern(
            cells=tuple(cell_list),
            total_sessions=total_sessions,
            total_minutes=total_minutes,
            strongest_window_label=strongest_window_label,
            strongest_window_minutes=strongest_window_minutes,
            window_session_count=window_session_count,
            status=status,
        )

    def build_highlights(self, patterns, comparison, sessions, range_definition):
        """Real, calculated personal highlights. None of these are invented:
        each one is derived from the current period's actual data."""
        best_day = None
        if patterns.best_day_name is not None:
            best_day = Highlight(
                title="Best Day",
                value=patterns.best_day_name,
                note=(
                    f"{format_minutes(patterns.best_day_focus_minutes)} "
                    "focused work"
                ),
            )

        longest_session = None
        best_session = None
        for session in sessions:
            minutes = max(0, int(session.get("actual_minutes") or 0))
            if minutes <= 0:
                continue
            if (
                best_session is None
                or minutes > best_session[0]
                or (
                    minutes == best_session[0]
                    and session.get("session_date") < best_session[1]
                )
            ):
                best_session = (minutes, session.get("session_date") or "")
        if best_session is not None:
            longest_session = Highlight(
                title="Longest Focus Session",
                value=format_minutes(best_session[0]),
                note=(
                    format_display_date(best_session[1])
                    if best_session[1]
                    else "This period"
                ),
            )

        improvement = None
        if comparison.percentage is not None and comparison.percentage > 0:
            improvement = Highlight(
                title="Biggest Improvement",
                value=f"+{comparison.percentage}%",
                note=(
                    "More focus than "
                    f"{self.COMPARISON_LABELS.get(range_definition.key, 'the previous period')}"
                ),
            )

        return HighlightsData(
            best_day=best_day,
            longest_session=longest_session,
            improvement=improvement,
        )

    def build_learned_insights(self, day_hour, patterns, consistency, calibration, daily_focus):
        """Generate evidence-backed observations about the user.

        Every insight follows: OBSERVATION + EVIDENCE + CONFIDENCE. Rules
        are deterministic, thresholds are documented above, and nothing is
        produced from weak signals. No LLM, no static motivational copy.
        """
        learned = []

        # --- Rhythm: strongest focus window --------------------------------
        if day_hour.status == "ready" and day_hour.strongest_window_label:
            share = (
                day_hour.strongest_window_minutes / day_hour.total_minutes
                if day_hour.total_minutes > 0
                else 0.0
            )
            confidence = (
                "high_confidence"
                if share >= self.RHYTHM_HIGH_SHARE
                else "moderate_confidence"
            )
            learned.append(
                LearnedInsight(
                    title="Focus Window",
                    description=(
                        f"You do your strongest focused work between "
                        f"{day_hour.strongest_window_label}."
                    ),
                    evidence=(
                        f"Based on {day_hour.window_session_count} "
                        "sessions"
                    ),
                    confidence=confidence,
                )
            )

        # --- Estimate pattern: strongest category bias --------------------
        category_candidates = []
        for category in calibration.categories:
            if (
                category.sample_count < self.CATEGORY_INSIGHT_MIN_SAMPLES
                or category.mean_relative_error is None
                or abs(category.mean_relative_error)
                < self.CATEGORY_INSIGHT_MIN_ERROR
            ):
                continue
            category_candidates.append(category)
        if category_candidates:
            strongest = max(
                category_candidates,
                key=lambda category: abs(category.mean_relative_error),
            )
            if strongest.bias == "underestimate":
                description = (
                    f"You consistently underestimate "
                    f"{strongest.activity_type} time."
                )
            else:
                description = (
                    f"You consistently overestimate "
                    f"{strongest.activity_type} time."
                )
            learned.append(
                LearnedInsight(
                    title="Estimate Pattern",
                    description=description,
                    evidence=(
                        f"Based on {strongest.sample_count} completed "
                        "activities"
                    ),
                    confidence=(
                        "moderate_confidence"
                        if strongest.sample_count
                        >= RECOMMENDATION_MIN_OBSERVATIONS
                        else "early_signal"
                    ),
                )
            )

        # --- Day pattern ---------------------------------------------------
        if (
            patterns.best_day_name is not None
            and patterns.active_days >= self.DAY_INSIGHT_MIN_ACTIVE_DAYS
            and patterns.best_day_focus_minutes
            >= self.DAY_INSIGHT_MIN_MINUTES
        ):
            learned.append(
                LearnedInsight(
                    title="Best Day",
                    description=(
                        f"{patterns.best_day_name} is currently your "
                        "strongest productivity day."
                    ),
                    evidence=(
                        f"{format_minutes(patterns.best_day_focus_minutes)} "
                        "focused in this period"
                    ),
                    confidence=(
                        "moderate_confidence"
                        if patterns.active_days >= 7
                        else "early_signal"
                    ),
                )
            )

        # --- Consistency: day-to-day variability ---------------------------
        halves = self.split_daily_focus_halves(daily_focus)
        if len(halves) == 2:
            older_cv, older_active = self.focus_variability(halves[0])
            newer_cv, newer_active = self.focus_variability(halves[1])
            if (
                older_cv is not None
                and newer_cv is not None
                and older_active >= self.CONSISTENCY_IMPROVEMENT_MIN_ACTIVE_HALF
                and newer_active >= self.CONSISTENCY_IMPROVEMENT_MIN_ACTIVE_HALF
                and newer_cv < older_cv * self.CONSISTENCY_IMPROVEMENT_RATIO
            ):
                learned.append(
                    LearnedInsight(
                        title="Growing Consistency",
                        description=(
                            "Your focus is becoming more consistent."
                        ),
                        evidence=(
                            f"Day-to-day variability fell from "
                            f"{round(older_cv * 100)}% to "
                            f"{round(newer_cv * 100)}%"
                        ),
                        confidence="moderate_confidence",
                    )
                )

        # --- Planning: estimates becoming more accurate --------------------
        planning_insight = self.build_planning_trend_insight()
        if planning_insight is not None:
            learned.append(planning_insight)

        return learned[:4]

    @staticmethod
    def split_daily_focus_halves(daily_focus):
        """Split the period's days into two equal halves for trend rules."""
        if not daily_focus:
            return []
        midpoint = len(daily_focus) // 2
        if midpoint == 0:
            return []
        return [daily_focus[:midpoint], daily_focus[midpoint:]]

    @staticmethod
    def focus_variability(days):
        """Return (coefficient of variation, active days) for daily focus.

        The coefficient of variation (std/mean) measures day-to-day
        consistency: a lower value means a steadier routine. Returns
        (None, 0) when the mean is zero.
        """
        minutes = [float(day.focus_minutes) for day in days]
        active = sum(1 for value in minutes if value > 0)
        if not minutes or sum(minutes) <= 0:
            return None, active
        average = mean(minutes)
        return pstdev(minutes) / average, active

    def build_planning_trend_insight(self):
        """Compare estimate accuracy between older and newer observations.

        Uses the same validity rule as calibration (original estimate and
        actual duration must both be positive) but is a separate read-only
        aggregation: the CalibrationService itself is not touched.
        """
        records = self.database.get_planning_trend_records()
        pairs = []
        for record in records:
            if not record.get("completed"):
                continue
            estimated = int(
                record.get("original_estimate_minutes")
                or record.get("estimated_minutes")
                or 0
            )
            actual = int(record.get("actual_minutes") or 0)
            if estimated <= 0 or actual <= 0:
                continue
            record_date = self.parse_record_date(record.get("date"))
            if record_date is None:
                continue
            pairs.append(
                (record_date, abs(actual - estimated) / estimated)
            )

        if len(pairs) < self.PLANNING_TREND_MIN_SAMPLES:
            return None

        pairs.sort(key=lambda item: item[0])
        midpoint = len(pairs) // 2
        older = [error for _, error in pairs[:midpoint]]
        newer = [error for _, error in pairs[midpoint:]]
        older_error = mean(older)
        newer_error = mean(newer)
        if older_error <= 0:
            return None
        if newer_error >= older_error * self.PLANNING_TREND_IMPROVEMENT_RATIO:
            return None

        return LearnedInsight(
            title="Sharper Estimates",
            description="Your estimates are becoming more accurate.",
            evidence=(
                f"Typical error dropped from "
                f"{format_plain_percent(older_error)} to "
                f"{format_plain_percent(newer_error)}"
            ),
            confidence="moderate_confidence",
        )

    def build_consistency(
        self,
        daily_focus,
        daily_goal_minutes,
        current_streak,
        best_streak,
    ):
        daily_goal_minutes = max(1, int(daily_goal_minutes or 0))
        heatmap_days = []
        goal_success_days = 0
        active_days = 0
        for daily in daily_focus:
            if daily.focus_minutes >= daily_goal_minutes:
                level = "high"
                goal_success_days += 1
            elif daily.focus_minutes >= round(daily_goal_minutes * 0.5):
                level = "moderate"
            elif daily.focus_minutes > 0 or daily.completed_tasks > 0:
                level = "light"
            else:
                level = "inactive"

            if level != "inactive":
                active_days += 1
            heatmap_days.append(
                HeatmapDay(
                    day=daily.day,
                    focus_minutes=daily.focus_minutes,
                    level=level,
                )
            )

        return ConsistencyData(
            heatmap_days=tuple(heatmap_days),
            current_streak=current_streak,
            best_streak=best_streak,
            active_days=active_days,
            period_days=len(daily_focus),
            goal_success_days=goal_success_days,
            daily_goal_minutes=daily_goal_minutes,
        )

    def generate_insights(
        self,
        overview,
        trend,
        patterns,
        consistency,
        calibration,
    ):
        insights = []
        comparison = trend.comparison
        has_current_work = (
            overview.completed_tasks > 0 or overview.focus_minutes > 0
        )
        has_previous_work = comparison.previous_focus_minutes > 0

        if not has_current_work and not has_previous_work:
            return [
                InsightItem(
                    kind="info",
                    title="Personal insights unlock with activity",
                    description=(
                        "Keep using Project Ascend. More activity will unlock "
                        "personalized insights."
                    ),
                )
            ]

        if comparison.percentage is not None and comparison.percentage >= 10:
            insights.append(
                InsightItem(
                    kind="positive",
                    title="Focus time is improving",
                    description=(
                        f"You focused {comparison.percentage}% more than the "
                        "previous equivalent period."
                    ),
                    metric=f"+{comparison.percentage}%",
                )
            )
        elif comparison.percentage is not None and comparison.percentage <= -10:
            insights.append(
                InsightItem(
                    kind="warning",
                    title="Focus time has dropped",
                    description=(
                        f"You focused {abs(comparison.percentage)}% less than "
                        "the previous equivalent period."
                    ),
                    metric=f"-{abs(comparison.percentage)}%",
                )
            )

        calibration_summary = calibration.summary
        if (
            calibration_summary.sample_count >= RECOMMENDATION_MIN_OBSERVATIONS
            and calibration_summary.mean_relative_error is not None
            and abs(calibration_summary.mean_relative_error) >= BIAS_BAND
        ):
            # Only a real, evidence-backed bias becomes an insight. Early
            # signals and balanced estimates stay quiet: the Planning
            # Accuracy section still shows the raw numbers.
            bias_percent = format_error_percent(
                calibration_summary.mean_relative_error
            )
            if calibration_summary.bias == "underestimate":
                insights.append(
                    InsightItem(
                        kind="recommendation",
                        title="Your estimates tend to run short",
                        description=(
                            f"Across {calibration_summary.sample_count} "
                            "completed activities you took "
                            f"{bias_percent} longer than planned on average. "
                            "Adding a buffer when planning makes your day "
                            "more realistic."
                        ),
                        metric=bias_percent,
                    )
                )
            elif calibration_summary.bias == "overestimate":
                insights.append(
                    InsightItem(
                        kind="recommendation",
                        title="Your estimates tend to run long",
                        description=(
                            f"Across {calibration_summary.sample_count} "
                            "completed activities you finished "
                            f"{bias_percent} sooner than planned on "
                            "average. The freed-up time can be planned for."
                        ),
                        metric=bias_percent,
                    )
                )

        if overview.total_tasks >= 3 and overview.completion_rate < 60:
            remaining_tasks = overview.total_tasks - overview.completed_tasks
            insights.append(
                InsightItem(
                    kind="warning",
                    title="Completion rate needs attention",
                    description=(
                        f"{remaining_tasks} planned activities remain unfinished "
                        "in this period."
                    ),
                    metric=f"{overview.completion_rate}%",
                )
            )

        if consistency.goal_success_days > 0:
            insights.append(
                InsightItem(
                    kind="goal",
                    title="You're hitting your daily focus goal.",
                    description=(
                        f"You met your {format_minutes(consistency.daily_goal_minutes)} "
                        f"daily goal on {consistency.goal_success_days} of "
                        f"{format_day_count(consistency.period_days)}."
                    ),
                    metric=(
                        f"{consistency.goal_success_days}/"
                        f"{format_day_count(consistency.period_days)}"
                    ),
                )
            )

        if patterns.best_time_label is not None:
            insights.append(
                InsightItem(
                    kind="pattern",
                    title="A strong focus window is emerging",
                    description=(
                        f"Your timestamped sessions are strongest between "
                        f"{patterns.best_time_label}."
                    ),
                    metric=format_minutes(patterns.best_time_focus_minutes),
                )
            )
        elif patterns.best_day_name is not None:
            insights.append(
                InsightItem(
                    kind="pattern",
                    title="Your strongest day is clear",
                    description=(
                        f"{patterns.best_day_name} has your highest focus time "
                        "in this period."
                    ),
                    metric=format_minutes(patterns.best_day_focus_minutes),
                )
            )

        if consistency.current_streak >= 3:
            insights.append(
                InsightItem(
                    kind="streak",
                    title="Your streak is holding",
                    description=(
                        f"You have maintained a {consistency.current_streak}-day "
                        "daily-goal streak."
                    ),
                    metric=format_day_count(consistency.current_streak),
                )
            )

        if (
            consistency.active_days > 0
            and consistency.active_days < consistency.period_days
            and len(insights) < 4
        ):
            missed_days = consistency.period_days - consistency.active_days
            inactive_verb = "was" if missed_days == 1 else "were"
            insights.append(
                InsightItem(
                    kind="recommendation",
                    title="Protect your next focus block",
                    description=(
                        f"{format_day_count(missed_days).capitalize()} "
                        f"{inactive_verb} inactive. A short planned "
                        "session can make the routine easier to sustain."
                    ),
                )
            )

        if not insights:
            insights.append(
                InsightItem(
                    kind="info",
                    title="Keep building your baseline",
                    description=(
                        "Complete a few more focus sessions to unlock stronger "
                        "comparisons and patterns."
                    ),
                )
            )
        return insights[:4]

    def calculate_xp_earned(
        self,
        current_events,
    ):
        return sum(int(event.get("amount") or 0) for event in current_events), None

    @staticmethod
    def calculate_percentage(numerator, denominator):
        if denominator <= 0:
            return 0
        return round((numerator / denominator) * 100)

    @staticmethod
    def parse_record_date(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def parse_timestamp(value):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def format_hour_block(hour):
        return f"{format_clock_hour(hour)} - {format_clock_hour((hour + 2) % 24)}"


def comparison_caption(range_definition):
    """Short context line describing the selected period's comparison.

    All Time has no previous equivalent period, so the caption simply says
    what the range contains instead of inventing a comparison.
    """
    if range_definition.previous_start_date is None:
        return "All recorded activity"
    previous_label = InsightsService.COMPARISON_LABELS.get(
        range_definition.key,
        "previous period",
    )
    return f"{range_definition.label} vs {previous_label}"


def format_minutes(minutes):
    """Return a compact human-readable duration for Insights presentation."""
    minutes = max(0, int(minutes or 0))
    hours, remaining_minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {remaining_minutes}m"
    return f"{remaining_minutes}m"


def format_day_count(count):
    """Return a grammatically correct Insights day count."""
    count = max(0, int(count or 0))
    noun = "day" if count == 1 else "days"
    return f"{count} {noun}"


def format_clock_hour(hour):
    hour = hour % 24
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour} {suffix}"
