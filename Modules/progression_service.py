"""Progression Service — Central progression domain and event evaluation service."""

from Modules.character_manager import CharacterManager, get_evolution_stage
from Modules.achievement_manager import ACHIEVEMENT_DEFINITIONS, MILESTONE_CATALOG


class ProgressionService:
    """Central domain read and evaluation layer for player progression."""

    def __init__(self, database, xp_manager, streak_manager, achievement_manager, character_manager=None):
        self.database = database
        self.xp_manager = xp_manager
        self.streak_manager = streak_manager
        self.achievement_manager = achievement_manager
        self.character_manager = character_manager or CharacterManager(database)

    def get_total_xp(self):
        """Return total XP from authoritative ledger."""
        return self.xp_manager.get_total_xp()

    def get_current_level(self):
        """Return current level derived strictly from total XP."""
        return self.xp_manager.get_level()

    def get_level_progress(self):
        """Return (level, xp_into_level, xp_for_level, xp_remaining)."""
        return self.xp_manager.get_level_progress()

    def get_evolution_stage(self):
        """Return evolution stage dictionary derived from current level."""
        return get_evolution_stage(self.get_current_level())

    def get_selected_character(self):
        """Return current character definition dictionary."""
        return self.character_manager.get_selected_character()

    def get_progression_summary(self):
        """Return comprehensive progression summary dictionary for UI consumption."""
        total_xp = self.get_total_xp()
        level, xp_into, xp_for, xp_rem = self.get_level_progress()
        evolution = self.get_evolution_stage()
        selected_char = self.get_selected_character()

        current_streak = self.streak_manager.get_current_streak()
        longest_streak = self.streak_manager.get_longest_streak()
        total_goal_days = self.streak_manager.get_total_goal_days()
        completion_rate = self.streak_manager.get_completion_rate()

        unlocked_ids = self.achievement_manager.get_unlocked_ids()
        milestone_history = self.database.get_milestone_history()

        return {
            "total_xp": total_xp,
            "level": level,
            "xp_into_level": xp_into,
            "xp_for_level": xp_for,
            "xp_remaining": xp_rem,
            "evolution_stage": evolution["stage"],
            "evolution_name": evolution["name"],
            "evolution_info": evolution,
            "character": selected_char,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_goal_days": total_goal_days,
            "completion_rate": completion_rate,
            "unlocked_achievements_count": len(unlocked_ids),
            "total_achievements_count": len(ACHIEVEMENT_DEFINITIONS),
            "milestones_reached_count": len(milestone_history),
        }

    def evaluate_achievements(self, trigger_event="manual"):
        """Run deterministic achievement evaluation and return newly unlocked definitions."""
        return self.achievement_manager.evaluate_achievements(trigger_event=trigger_event)

    def evaluate_milestones(self, trigger_event="manual"):
        """Run deterministic milestone evaluation and return newly reached tier definitions."""
        return self.achievement_manager.evaluate_milestones(trigger_event=trigger_event)

    def check_progression_events(self, trigger_event="manual"):
        """Run full evaluation, record level reaches, and return a dictionary of progression updates."""
        # 1. Sync & reconcile XP cache
        total_xp = self.get_total_xp()

        # 2. Check level reaches
        new_levels_recorded = self.database.check_and_record_level_reaches(
            total_xp,
            timestamp=trigger_event
        )

        # 3. Evaluate achievements and milestones
        new_achievements = self.evaluate_achievements(trigger_event=trigger_event)
        new_milestones = self.evaluate_milestones(trigger_event=trigger_event)

        level, xp_into, xp_for, xp_rem = self.get_level_progress()
        evolution = get_evolution_stage(level)

        return {
            "total_xp": total_xp,
            "current_level": level,
            "evolution_stage": evolution["stage"],
            "new_levels_recorded": new_levels_recorded,
            "new_achievements": new_achievements,
            "new_milestones": new_milestones,
            "trigger_event": trigger_event,
        }
