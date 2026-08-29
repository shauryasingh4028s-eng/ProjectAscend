"""Persistent Achievement & Milestone Evaluation System."""

from datetime import datetime, date

ACHIEVEMENT_DEFINITIONS = {
    "consistency_first_step": {
        "id": "consistency_first_step",
        "name": "First Ascend",
        "description": "Complete your first daily focus goal.",
        "category": "Consistency",
        "icon": "🎯",
    },
    "consistency_streak_3": {
        "id": "consistency_streak_3",
        "name": "Three-Fold Focus",
        "description": "Maintain a 3-day focus goal streak.",
        "category": "Consistency",
        "icon": "🔥",
    },
    "consistency_streak_7": {
        "id": "consistency_streak_7",
        "name": "Week of Power",
        "description": "Maintain a 7-day focus goal streak.",
        "category": "Consistency",
        "icon": "⚡",
    },
    "consistency_streak_30": {
        "id": "consistency_streak_30",
        "name": "Iron Will",
        "description": "Maintain a 30-day focus goal streak.",
        "category": "Consistency",
        "icon": "👑",
    },
    "deepwork_10h": {
        "id": "deepwork_10h",
        "name": "Deep Dive",
        "description": "Log 10 total hours of focus sessions.",
        "category": "Deep Work",
        "icon": "⏱",
    },
    "deepwork_50h": {
        "id": "deepwork_50h",
        "name": "Flow Master",
        "description": "Log 50 total hours of focus sessions.",
        "category": "Deep Work",
        "icon": "🌊",
    },
    "deepwork_100h": {
        "id": "deepwork_100h",
        "name": "Ascended Focus",
        "description": "Log 100 total hours of focus sessions.",
        "category": "Deep Work",
        "icon": "🌌",
    },
    "planning_perfect_day": {
        "id": "planning_perfect_day",
        "name": "Master Planner",
        "description": "Complete 100% of planned tasks in a day.",
        "category": "Planning",
        "icon": "📋",
    },
    "mastery_level_10": {
        "id": "mastery_level_10",
        "name": "Horizon Reached",
        "description": "Reach Level 10.",
        "category": "Mastery",
        "icon": "🏛",
    },
    "mastery_level_25": {
        "id": "mastery_level_25",
        "name": "Vanguard Status",
        "description": "Reach Level 25.",
        "category": "Mastery",
        "icon": "🛡",
    },
    "mastery_level_50": {
        "id": "mastery_level_50",
        "name": "Sovereign Ascent",
        "description": "Reach Level 50.",
        "category": "Mastery",
        "icon": "✨",
    },
}

MILESTONE_CATALOG = {
    "focus_duration": {
        "name": "Focus Duration",
        "unit": "hours",
        "icon": "⏱",
        "tiers": [
            {"tier": 1, "threshold": 600, "label": "10h Focus"},      # 600 mins = 10h
            {"tier": 2, "threshold": 3000, "label": "50h Focus"},     # 3000 mins = 50h
            {"tier": 3, "threshold": 6000, "label": "100h Focus"},    # 6000 mins = 100h
            {"tier": 4, "threshold": 15000, "label": "250h Focus"},   # 15000 mins = 250h
            {"tier": 5, "threshold": 30000, "label": "500h Focus"},   # 30000 mins = 500h
        ],
    },
    "completed_activities": {
        "name": "Completed Activities",
        "unit": "tasks",
        "icon": "✅",
        "tiers": [
            {"tier": 1, "threshold": 10, "label": "10 Tasks"},
            {"tier": 2, "threshold": 50, "label": "50 Tasks"},
            {"tier": 3, "threshold": 100, "label": "100 Tasks"},
            {"tier": 4, "threshold": 250, "label": "250 Tasks"},
            {"tier": 5, "threshold": 500, "label": "500 Tasks"},
        ],
    },
    "daily_goal_days": {
        "name": "Daily Goal Days",
        "unit": "days",
        "icon": "🎯",
        "tiers": [
            {"tier": 1, "threshold": 1, "label": "1 Goal Day"},
            {"tier": 2, "threshold": 7, "label": "7 Goal Days"},
            {"tier": 3, "threshold": 30, "label": "30 Goal Days"},
            {"tier": 4, "threshold": 90, "label": "90 Goal Days"},
            {"tier": 5, "threshold": 180, "label": "180 Goal Days"},
        ],
    },
    "longest_streak": {
        "name": "Longest Streak",
        "unit": "days",
        "icon": "🔥",
        "tiers": [
            {"tier": 1, "threshold": 3, "label": "3-Day Streak"},
            {"tier": 2, "threshold": 7, "label": "7-Day Streak"},
            {"tier": 3, "threshold": 14, "label": "14-Day Streak"},
            {"tier": 4, "threshold": 30, "label": "30-Day Streak"},
            {"tier": 5, "threshold": 60, "label": "60-Day Streak"},
        ],
    },
}


class AchievementManager:
    """Evaluates and persists achievements and milestones without XP inflation."""

    def __init__(self, database, streak_manager, xp_manager):
        self.database = database
        self.streak_manager = streak_manager
        self.xp_manager = xp_manager

    def get_unlocked_ids(self):
        """Return set of achievement IDs already unlocked in the database."""
        unlocked_rows = self.database.get_unlocked_achievements()
        return {
            row["achievement_id"] if isinstance(row, dict) else row[0]
            for row in unlocked_rows
        }

    def get_unlocked(self):
        """Legacy helper: Return list of unlocked achievement display names/titles."""
        unlocked_ids = self.get_unlocked_ids()
        # Also run evaluation so newly qualified ones are caught
        self.evaluate_achievements()
        unlocked_ids = self.get_unlocked_ids()
        return [ACHIEVEMENT_DEFINITIONS[aid]["name"] for aid in unlocked_ids if aid in ACHIEVEMENT_DEFINITIONS]

    def evaluate_achievements(self, trigger_event="manual"):
        """Deterministically check all achievement criteria and persist new unlocks."""
        unlocked_ids = self.get_unlocked_ids()
        already_unlocked = set(unlocked_ids)

        current_level = self.xp_manager.get_level()
        current_streak = self.streak_manager.get_current_streak()
        longest_streak = self.streak_manager.get_longest_streak()
        total_goal_days = self.streak_manager.get_total_goal_days()
        total_focus_minutes = self.database.get_total_focus_minutes()
        completed_tasks, total_tasks = self.database.get_today_task_completion_status()

        # Check conditions
        to_unlock = []

        if total_goal_days >= 1 and "consistency_first_step" not in already_unlocked:
            to_unlock.append("consistency_first_step")

        if current_streak >= 3 and "consistency_streak_3" not in already_unlocked:
            to_unlock.append("consistency_streak_3")

        if current_streak >= 7 and "consistency_streak_7" not in already_unlocked:
            to_unlock.append("consistency_streak_7")

        if current_streak >= 30 and "consistency_streak_30" not in already_unlocked:
            to_unlock.append("consistency_streak_30")

        if total_focus_minutes >= 600 and "deepwork_10h" not in already_unlocked:
            to_unlock.append("deepwork_10h")

        if total_focus_minutes >= 3000 and "deepwork_50h" not in already_unlocked:
            to_unlock.append("deepwork_50h")

        if total_focus_minutes >= 6000 and "deepwork_100h" not in already_unlocked:
            to_unlock.append("deepwork_100h")

        if total_tasks >= 3 and completed_tasks == total_tasks and "planning_perfect_day" not in already_unlocked:
            to_unlock.append("planning_perfect_day")

        if current_level >= 10 and "mastery_level_10" not in already_unlocked:
            to_unlock.append("mastery_level_10")

        if current_level >= 25 and "mastery_level_25" not in already_unlocked:
            to_unlock.append("mastery_level_25")

        if current_level >= 50 and "mastery_level_50" not in already_unlocked:
            to_unlock.append("mastery_level_50")

        newly_unlocked_defs = []
        for aid in to_unlock:
            success = self.database.unlock_achievement(aid, trigger_event=trigger_event)
            if success and aid in ACHIEVEMENT_DEFINITIONS:
                newly_unlocked_defs.append(ACHIEVEMENT_DEFINITIONS[aid])

        return newly_unlocked_defs

    def evaluate_milestones(self, trigger_event="manual"):
        """Deterministically check all milestone criteria and persist new reached tiers."""
        history_rows = self.database.get_milestone_history()
        reached_set = {
            (row["milestone_id"], row["tier"]) if isinstance(row, dict) else (row[0], row[1])
            for row in history_rows
        }

        total_focus_minutes = self.database.get_total_focus_minutes()
        total_completed_activities = self.database.get_total_completed_activities()
        total_goal_days = self.streak_manager.get_total_goal_days()
        longest_streak = self.streak_manager.get_longest_streak()

        current_metrics = {
            "focus_duration": total_focus_minutes,
            "completed_activities": total_completed_activities,
            "daily_goal_days": total_goal_days,
            "longest_streak": longest_streak,
        }

        newly_reached_tiers = []
        now_str = datetime.now().isoformat()

        for milestone_id, cat_info in MILESTONE_CATALOG.items():
            val = current_metrics.get(milestone_id, 0)
            for tier_info in cat_info["tiers"]:
                t = tier_info["tier"]
                thresh = tier_info["threshold"]
                if val >= thresh and (milestone_id, t) not in reached_set:
                    success = self.database.record_milestone_reach(milestone_id, t, now_str)
                    if success:
                        newly_reached_tiers.append({
                            "milestone_id": milestone_id,
                            "milestone_name": cat_info["name"],
                            "tier": t,
                            "label": tier_info["label"],
                            "threshold": thresh,
                            "reached_at": now_str,
                        })

        return newly_reached_tiers