# Constant for legacy backwards compatibility
XP_PER_LEVEL = 100


def calculate_level_from_xp(total_xp: int) -> int:
    """Calculate current user level based on the approved tiered linear curve.

    - Level 1: 0 XP
    - Levels 2–10: 100 XP per level (Cumulative at L10 = 900 XP)
    - Levels 11–50: 250 XP per level (Cumulative at L50 = 10,900 XP)
    - Levels 51+: 500 XP per level (Cumulative at L100 = 35,900 XP)
    """
    total_xp = max(0, int(total_xp))
    if total_xp < 900:
        return (total_xp // 100) + 1
    elif total_xp < 10900:
        return 10 + ((total_xp - 900) // 250)
    else:
        return 50 + ((total_xp - 10900) // 500)


def get_level_threshold(level: int) -> int:
    """Return the cumulative XP required to reach the given 1-indexed level."""
    level = max(1, int(level))
    if level <= 10:
        return (level - 1) * 100
    elif level <= 50:
        return 900 + (level - 10) * 250
    else:
        return 10900 + (level - 50) * 500


def get_level_progress(total_xp: int):
    """Return (level, xp_into_level, xp_for_level, xp_remaining)."""
    total_xp = max(0, int(total_xp))
    level = calculate_level_from_xp(total_xp)
    current_threshold = get_level_threshold(level)
    next_threshold = get_level_threshold(level + 1)
    xp_for_level = next_threshold - current_threshold
    xp_into_level = total_xp - current_threshold
    xp_remaining = xp_for_level - xp_into_level
    return level, xp_into_level, xp_for_level, xp_remaining


class XPManager:
    """Manages XP accumulation, level progression, and event awards."""

    def __init__(self, database):
        self.database = database

    def get_total_xp(self):
        """Read authoritative total XP directly from the database ledger and repair cache."""
        return self.database.sync_total_xp_cache()

    def get_level(self):
        """Calculate the user's level based on the tiered linear curve."""
        return calculate_level_from_xp(self.get_total_xp())

    def get_level_progress(self):
        """Return full level progress tuple: (level, xp_into_level, xp_for_level, xp_remaining)."""
        return get_level_progress(self.get_total_xp())

    def award_activity_completion(self, activity_id=None):
        """Award +10 XP for completing an activity with idempotent duplicate protection."""
        if activity_id is not None:
            return self.database.award_activity_completion_xp(activity_id, 10)
        return self.get_total_xp()

    def void_activity_completion(self, activity_id=None):
        """Record a compensating void event (-10 XP) if an awarded activity is uncompleted or deleted."""
        if activity_id is not None:
            return self.database.void_activity_completion_xp(activity_id)
        return self.get_total_xp()

    def award_daily_goal(self, earned_date=None):
        """Award +50 XP for completing the daily study goal (max 1 per calendar date)."""
        return self.database.award_daily_goal_xp(earned_date, 50)
