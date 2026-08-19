"""Persistent, evidence-based achievement evaluation."""

from dataclasses import dataclass

from Modules.gamification_config import ACHIEVEMENTS, AchievementDefinition
from Modules.progression_metrics import collect_progress_metrics


@dataclass(frozen=True)
class AchievementState:
    definition: AchievementDefinition
    unlocked: bool
    unlocked_at: str | None
    current_value: int | float


class AchievementManager:
    def __init__(self, database, streak_manager, xp_manager):
        self.database = database
        self.streak_manager = streak_manager
        self.xp_manager = xp_manager

    def _metrics(self):
        return collect_progress_metrics(
            self.database,
            self.streak_manager,
            self.xp_manager,
        )

    def evaluate(self, metrics=None):
        """Persist newly satisfied achievements and return their definitions."""
        metrics = metrics or self._metrics()
        existing = self.database.get_achievement_unlocks()
        newly_unlocked = []

        for achievement in ACHIEVEMENTS:
            if achievement.identifier in existing:
                continue
            if metrics.value_for(achievement.metric) < achievement.threshold:
                continue
            if self.database.unlock_achievement(achievement.identifier):
                newly_unlocked.append(achievement)

        return tuple(newly_unlocked)

    def get_states(self, metrics=None, evaluate=True):
        metrics = metrics or self._metrics()
        if evaluate:
            self.evaluate(metrics)
        unlocks = self.database.get_achievement_unlocks()
        return tuple(
            AchievementState(
                definition=achievement,
                unlocked=achievement.identifier in unlocks,
                unlocked_at=unlocks.get(achievement.identifier),
                current_value=metrics.value_for(achievement.metric),
            )
            for achievement in ACHIEVEMENTS
        )

    def get_unlocked_records(self, metrics=None):
        return tuple(
            state for state in self.get_states(metrics) if state.unlocked
        )

    def get_unlocked(self):
        """Compatibility API used by the legacy completion screen."""
        return [
            state.definition.name
            for state in self.get_unlocked_records()
        ]
