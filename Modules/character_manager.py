"""Character Identity Architecture & Cosmetic Evolution Engine."""

import os
from pathlib import Path

CHARACTER_DEFINITIONS = {
    "architect": {
        "id": "architect",
        "name": "The Architect",
        "title": "Focus & Planning Mastery",
        "description": "Master of structure, vision, and strategic focus.",
        "icon": "📐",
    },
    "catalyst": {
        "id": "catalyst",
        "name": "The Catalyst",
        "title": "Execution & Speed Mastery",
        "description": "Spark of momentum, high output, and swift execution.",
        "icon": "⚡",
    },
    "sentinel": {
        "id": "sentinel",
        "name": "The Sentinel",
        "title": "Consistency & Habit Mastery",
        "description": "Guardian of daily routines, endurance, and unbroken streaks.",
        "icon": "🛡",
    },
    "vanguard": {
        "id": "vanguard",
        "name": "The Vanguard",
        "title": "Deep Work & Endurance Mastery",
        "description": "Pioneer of long flow states and deep cognitive focus.",
        "icon": "⚔",
    },
    "scholar": {
        "id": "scholar",
        "name": "The Scholar",
        "title": "Knowledge & Reflection Mastery",
        "description": "Seeker of continuous learning, research, and deep insight.",
        "icon": "📜",
    },
    "pathfinder": {
        "id": "pathfinder",
        "name": "The Pathfinder",
        "title": "Goal Exploration & Direction",
        "description": "Navigator of milestone pathways and new horizons.",
        "icon": "🧭",
    },
    "artisan": {
        "id": "artisan",
        "name": "The Artisan",
        "title": "Craft & Precision Execution",
        "description": "Craftsman of meticulous detail and pristine completion quality.",
        "icon": "🎨",
    },
    "paragon": {
        "id": "paragon",
        "name": "The Paragon",
        "title": "Balanced Holistic Mastery",
        "description": "Embodiment of harmony across planning, focus, and consistency.",
        "icon": "👑",
    },
}

DEFAULT_CHARACTER_ID = "architect"


def get_evolution_stage(level: int) -> dict:
    """Return the evolution stage dictionary derived strictly from current level."""
    level = max(1, int(level))
    if level < 10:
        return {
            "stage": 1,
            "name": "Initiated",
            "min_level": 1,
            "required_xp": 0,
            "next_stage_level": 10,
        }
    elif level < 25:
        return {
            "stage": 2,
            "name": "Established",
            "min_level": 10,
            "required_xp": 900,
            "next_stage_level": 25,
        }
    elif level < 50:
        return {
            "stage": 3,
            "name": "Ascended",
            "min_level": 25,
            "required_xp": 4650,
            "next_stage_level": 50,
        }
    else:
        return {
            "stage": 4,
            "name": "Sovereign",
            "min_level": 50,
            "required_xp": 10900,
            "next_stage_level": None,
        }


class CharacterManager:
    """Manages character identity, cosmetic selection, and visual evolution paths."""

    def __init__(self, database):
        self.database = database

    def get_characters(self):
        """Return list of all 8 character definition dictionaries."""
        return list(CHARACTER_DEFINITIONS.values())

    def get_character_definition(self, character_id):
        """Return definition dictionary for character_id, or default if invalid."""
        return CHARACTER_DEFINITIONS.get(character_id, CHARACTER_DEFINITIONS[DEFAULT_CHARACTER_ID])

    def get_selected_character_id(self):
        """Read selected character ID from user_progression_profile (defaults to 'architect')."""
        selected = self.database.get_progression_setting("selected_character_id", DEFAULT_CHARACTER_ID)
        if selected not in CHARACTER_DEFINITIONS:
            selected = DEFAULT_CHARACTER_ID
            self.database.set_progression_setting("selected_character_id", selected)
        return selected

    def get_selected_character(self):
        """Return definition dictionary for the currently selected character."""
        char_id = self.get_selected_character_id()
        return self.get_character_definition(char_id)

    def set_selected_character(self, character_id):
        """Persist selected character_id if valid."""
        if character_id in CHARACTER_DEFINITIONS:
            self.database.set_progression_setting("selected_character_id", character_id)
            return True
        return False

    def get_character_asset_path(self, character_id, stage=1, base_dir=None):
        """Return normalized relative/absolute asset path for character stage with graceful fallback."""
        if character_id not in CHARACTER_DEFINITIONS:
            character_id = DEFAULT_CHARACTER_ID
        stage = max(1, min(int(stage), 4))

        if base_dir is None:
            rel_path = f"assets/characters/{character_id}/stage_{stage}.png"
        else:
            rel_path = str(Path(base_dir) / "assets" / "characters" / character_id / f"stage_{stage}.png")

        return rel_path
