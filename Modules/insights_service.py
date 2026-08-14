"""Persisted-data analytics and insight generation for Project Ascend."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from Modules.calibration_service import (
    BIAS_BAND,
    RECOMMENDATION_MIN_OBSERVATIONS,
    CalibrationReport,
    CalibrationService,
    format_error_percent,
)


@dataclass(frozen=True)
class RangeDefinition:
    key: str
    label: str
    start_date: date
    end_date: date
    previous_start_date: date
    previous_end_date: date


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
    insights: tuple[InsightItem, ...]


class InsightsService:
    """Build one complete Insights view model from a persisted data snapshot."""

    RANGE_DAYS = {
        "today": 1,
        "7_days": 7,
        "30_days": 30,
    }

    def __init__(self, database, streak_manager):
        self.database = database
        self.streak_manager = streak_manager
        self.calibration_service = CalibrationService(database)

    def build_dashboard(self, range_key="7_days", today=None):
        """Return all analytics needed to render one selected Insights range."""
        range_definition = self.get_range_definition(range_key, today)
        records = self.database.get_insights_records(
            range_definition.previous_start_date.isoformat(),
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
        )
        current_focus = sum(item.focus_minutes for item in current_days)
        previous_focus = sum(item.focus_minutes for item in previous_days)
        completed_tasks = sum(item.completed_tasks for item in current_days)
        total_tasks = sum(item.total_tasks for item in current_days)
        current_streak = self.streak_manager.get_current_streak()
        best_streak = self.streak_manager.get_longest_streak()
        xp_earned, xp_status = self.calculate_xp_earned(
            current_xp_events,
        )

        overview = OverviewData(
            focus_minutes=current_focus,
            completed_tasks=completed_tasks,
            total_tasks=total_tasks,
            completion_rate=self.calculate_percentage(completed_tasks, total_tasks),
            current_streak=current_streak,
            xp_earned=xp_earned,
            xp_status=xp_status,
        )
        trend = FocusTrendData(
            points=tuple(current_days),
            total_focus_minutes=current_focus,
            daily_average_minutes=round(
                current_focus / len(current_days)
            ) if current_days else 0,
            comparison=self.build_comparison(
                current_focus,
                previous_focus,
                range_definition,
            ),
        )
        patterns = self.build_patterns(
            current_days,
            current_activities,
            current_sessions,
        )
        consistency = self.build_consistency(
            current_days,
            records["daily_goal_minutes"],
            current_streak,
            best_streak,
        )
        calibration = self.calibration_service.build_report(today)

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
            insights=tuple(insights),
        )

    def get_range_definition(self, range_key, today=None):
        if range_key not in self.RANGE_DAYS:
            range_key = "7_days"

        end_date = today or date.today()
        period_days = self.RANGE_DAYS[range_key]
        start_date = end_date - timedelta(days=period_days - 1)
        previous_end_date = start_date - timedelta(days=1)
        previous_start_date = previous_end_date - timedelta(
            days=period_days - 1
        )
        labels = {
            "today": "Today",
            "7_days": "7 Days",
            "30_days": "30 Days",
        }
        return RangeDefinition(
            key=range_key,
            label=labels[range_key],
            start_date=start_date,
            end_date=end_date,
            previous_start_date=previous_start_date,
            previous_end_date=previous_end_date,
        )

    def partition_records(self, records, date_key, range_definition):
        current_records = []
        previous_records = []
        for record in records:
            record_date = self.parse_record_date(record.get(date_key))
            if record_date is None:
                continue
            if range_definition.start_date <= record_date <= range_definition.end_date:
                current_records.append(record)
            elif (
                range_definition.previous_start_date
                <= record_date
                <= range_definition.previous_end_date
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
        period_label = {
            "today": "previous day",
            "7_days": "previous week",
            "30_days": "previous 30 days",
        }[range_definition.key]

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
