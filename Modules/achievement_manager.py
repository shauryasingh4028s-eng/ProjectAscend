class AchievementManager:
    def __init__(self, database, streak_manager, xp_manager):
        # Shared managers.
        self.database = database
        self.streak_manager = streak_manager
        self.xp_manager = xp_manager

    def get_unlocked(self):
        achievements = []

        total_xp = self.xp_manager.get_total_xp()
        current_streak = self.streak_manager.get_current_streak()
        total_goal_days = self.streak_manager.get_total_goal_days()

        if total_goal_days >= 1:
            achievements.append("🎯 First Goal")

        if current_streak >= 3:
            achievements.append("🔥 3 Day Streak")

        if current_streak >= 7:
            achievements.append("🔥 7 Day Streak")

        if current_streak >= 30:
            achievements.append("👑 30 Day Streak")

        if total_xp >= 100:
            achievements.append("⭐ Level 2")

        if total_xp >= 500:
            achievements.append("🌟 Rising Star")

        if total_xp >= 1000:
            achievements.append("🏆 Ascended")

        return achievements