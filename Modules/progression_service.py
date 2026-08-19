"""Coordinates existing productivity facts into one coherent progression flow."""

from dataclasses import dataclass
from datetime import date

from Modules.gamification_config import rank_for_level
from Modules.progression_metrics import ProgressMetrics, collect_progress_metrics


@dataclass(frozen=True)
class ProgressionUpdate:
    activity_date: str
    xp_before: int
    xp_after: int
    activity_xp_awarded: bool
    daily_goal_xp_awarded: bool
    level_before: int
    level_after: int
    stage_before: str
    stage_after: str
    achievements: tuple
    milestones: tuple

    @property
    def xp_earned(self):
        return self.xp_after - self.xp_before

    @property
    def leveled_up(self):
        return self.level_after > self.level_before

    @property
    def character_evolved(self):
        return self.stage_after != self.stage_before

    @property
    def has_celebration(self):
        return bool(
            self.leveled_up
            or self.daily_goal_xp_awarded
            or self.achievements
            or self.milestones
        )


@dataclass(frozen=True)
class ProgressionSnapshot:
    metrics: ProgressMetrics
    rank: object
    character: object
    evolution_stage: object
    achievements: tuple
    milestones: tuple


class ProgressionService:
    """Orchestrates managers without replacing any productivity source."""

    def __init__(
        self,
        database,
        xp_manager,
        streak_manager,
        achievement_manager,
        milestone_manager,
        character_manager,
    ):
        self.database = database
        self.xp_manager = xp_manager
        self.streak_manager = streak_manager
        self.achievement_manager = achievement_manager
        self.milestone_manager = milestone_manager
        self.character_manager = character_manager

    def collect_metrics(self):
        return collect_progress_metrics(
            self.database,
            self.streak_manager,
            self.xp_manager,
        )

    def reconcile_existing_progress(self):
        """Persist earned legacy progress without inventing historical dates."""
        metrics = self.collect_metrics()
        self.achievement_manager.evaluate(metrics)
        self.milestone_manager.evaluate(metrics)
        return metrics

    def process_activity_completion(self, activity_id, activity_date=None):
        """Apply all one-time progression resulting from a completed activity."""
        xp_before = self.xp_manager.get_total_xp()
        level_before = self.xp_manager.get_level()
        stage_before = self.character_manager.get_evolution_stage(
            level_before
        ).identifier

        activity_date = activity_date or date.today().isoformat()
        activity_award = self.xp_manager.award_activity_completion_result(
            activity_id
        )
        goal_award = self.xp_manager.award_daily_goal_result(activity_date)

        metrics = self.collect_metrics()
        achievements = self.achievement_manager.evaluate(metrics)
        milestones = self.milestone_manager.evaluate(metrics)
        level_after = metrics.level
        stage_after = self.character_manager.get_evolution_stage(
            level_after
        ).identifier

        return ProgressionUpdate(
            activity_date=str(activity_date),
            xp_before=xp_before,
            xp_after=metrics.total_xp,
            activity_xp_awarded=activity_award.awarded,
            daily_goal_xp_awarded=goal_award.awarded,
            level_before=level_before,
            level_after=level_after,
            stage_before=stage_before,
            stage_after=stage_after,
            achievements=achievements,
            milestones=milestones,
        )

    def snapshot(self):
        metrics = self.collect_metrics()
        # Direct database changes and migration-era data are safely reconciled
        # when Player Progress opens; already unlocked rows are never repeated.
        self.achievement_manager.evaluate(metrics)
        self.milestone_manager.evaluate(metrics)
        return ProgressionSnapshot(
            metrics=metrics,
            rank=rank_for_level(metrics.level),
            character=self.character_manager.get_selected(),
            evolution_stage=self.character_manager.get_evolution_stage(
                metrics.level
            ),
            achievements=self.achievement_manager.get_states(
                metrics,
                evaluate=False,
            ),
            milestones=self.milestone_manager.get_states(
                metrics,
                evaluate=False,
            ),
        )
