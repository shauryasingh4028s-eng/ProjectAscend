"""Single source of truth for Project Ascend XP and level calculations."""

from dataclasses import dataclass
from datetime import date

from Modules.gamification_config import (
    ACTIVITY_COMPLETION_XP,
    DAILY_GOAL_XP,
    XP_PER_LEVEL,
    level_for_xp,
    rank_for_level,
    xp_into_level,
)


@dataclass(frozen=True)
class XPAwardResult:
    total_xp: int
    amount: int
    awarded: bool
    event_type: str


class XPManager:
    def __init__(self, database):
        self.database = database

    def get_total_xp(self):
        """Read the existing persisted total without recalculating history."""
        xp = self.database.get_setting("total_xp")
        if xp is None:
            self.database.set_setting("total_xp", 0)
            return 0
        try:
            return max(0, int(xp))
        except (TypeError, ValueError):
            return 0

    def get_level(self):
        return level_for_xp(self.get_total_xp())

    def get_rank(self):
        return rank_for_level(self.get_level())

    def get_xp_into_level(self):
        return xp_into_level(self.get_total_xp())

    def get_xp_to_next_level(self):
        return XP_PER_LEVEL - self.get_xp_into_level()

    def award_activity_completion_result(self, activity_id=None):
        """Award the established 10 XP completion reward once per activity."""
        if activity_id is None:
            # v1.5 no longer permits unkeyed completion rewards: without a
            # persisted activity there is no real behaviour to verify.
            return XPAwardResult(
                self.get_total_xp(), 0, False, "activity_completion"
            )

        total_xp, awarded = self.database.award_activity_completion_xp_result(
            activity_id,
            ACTIVITY_COMPLETION_XP,
        )
        return XPAwardResult(
            total_xp,
            ACTIVITY_COMPLETION_XP if awarded else 0,
            awarded,
            "activity_completion",
        )

    def award_activity_completion(self, activity_id=None):
        """Compatibility API returning the persisted total XP."""
        return self.award_activity_completion_result(activity_id).total_xp

    def award_daily_goal_result(self, activity_date=None):
        """Award daily-goal XP only when daily history proves the goal."""
        activity_date = activity_date or date.today().isoformat()
        total_xp, awarded = self.database.award_daily_goal_xp(
            activity_date,
            DAILY_GOAL_XP,
        )
        return XPAwardResult(
            total_xp,
            DAILY_GOAL_XP if awarded else 0,
            awarded,
            "daily_goal",
        )

    def award_daily_goal(self, activity_date=None):
        """Compatibility API returning the persisted total XP."""
        return self.award_daily_goal_result(activity_date).total_xp
