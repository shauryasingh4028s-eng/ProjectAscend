"""Read-only aggregation of persisted productivity facts for progression."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressMetrics:
    total_xp: int
    level: int
    current_streak: int
    best_streak: int
    focus_minutes: int
    focus_sessions: int
    completed_activities: int
    goal_days: int
    recorded_days: int
    goal_completion_rate: float

    def value_for(self, metric_name):
        if not hasattr(self, metric_name):
            raise KeyError(f"Unsupported progression metric: {metric_name}")
        return getattr(self, metric_name)


def collect_progress_metrics(database, streak_manager, xp_manager):
    """Build one immutable snapshot from existing authoritative sources."""
    stored = database.get_progress_metrics()
    return ProgressMetrics(
        total_xp=xp_manager.get_total_xp(),
        level=xp_manager.get_level(),
        current_streak=streak_manager.get_current_streak(),
        best_streak=streak_manager.get_longest_streak(),
        focus_minutes=stored["focus_minutes"],
        focus_sessions=stored["focus_sessions"],
        completed_activities=stored["completed_activities"],
        goal_days=stored["goal_days"],
        recorded_days=stored["recorded_days"],
        goal_completion_rate=stored["goal_completion_rate"],
    )
