"""Broad, persistent progression tracks backed by real productivity data."""

from dataclasses import dataclass

from Modules.gamification_config import MILESTONE_TRACKS, MilestoneTrack
from Modules.progression_metrics import collect_progress_metrics


@dataclass(frozen=True)
class MilestoneUnlock:
    identifier: str
    track: MilestoneTrack
    tier: int
    threshold: int


@dataclass(frozen=True)
class MilestoneState:
    track: MilestoneTrack
    current_value: int | float
    completed_tiers: int
    next_threshold: int | None
    unlocked_at: str | None


class MilestoneManager:
    def __init__(self, database, streak_manager, xp_manager):
        self.database = database
        self.streak_manager = streak_manager
        self.xp_manager = xp_manager

    @staticmethod
    def milestone_id(track, tier):
        return f"{track.identifier}:tier_{tier}"

    def _metrics(self):
        return collect_progress_metrics(
            self.database,
            self.streak_manager,
            self.xp_manager,
        )

    def evaluate(self, metrics=None):
        metrics = metrics or self._metrics()
        existing = self.database.get_milestone_unlocks()
        newly_unlocked = []

        for track in MILESTONE_TRACKS:
            value = metrics.value_for(track.metric)
            for tier, threshold in enumerate(track.thresholds, start=1):
                identifier = self.milestone_id(track, tier)
                if identifier in existing or value < threshold:
                    continue
                if self.database.unlock_milestone(identifier):
                    newly_unlocked.append(
                        MilestoneUnlock(identifier, track, tier, threshold)
                    )

        return tuple(newly_unlocked)

    def get_states(self, metrics=None, evaluate=True):
        metrics = metrics or self._metrics()
        if evaluate:
            self.evaluate(metrics)
        unlocks = self.database.get_milestone_unlocks()
        states = []

        for track in MILESTONE_TRACKS:
            completed = 0
            latest_timestamp = None
            for tier, _threshold in enumerate(track.thresholds, start=1):
                timestamp = unlocks.get(self.milestone_id(track, tier))
                if timestamp is not None:
                    completed = tier
                    latest_timestamp = timestamp
            next_threshold = (
                track.thresholds[completed]
                if completed < len(track.thresholds)
                else None
            )
            states.append(
                MilestoneState(
                    track=track,
                    current_value=metrics.value_for(track.metric),
                    completed_tiers=completed,
                    next_threshold=next_threshold,
                    unlocked_at=latest_timestamp,
                )
            )

        return tuple(states)
