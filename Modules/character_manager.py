"""Persistent selection and derived visual evolution for Ascend characters."""

from Modules.gamification_config import (
    CHARACTER_BY_ID,
    DEFAULT_CHARACTER_ID,
    evolution_stage_for_level,
)


SELECTED_CHARACTER_SETTING = "selected_character"


class CharacterManager:
    def __init__(self, database):
        self.database = database

    def get_selected_id(self):
        selected = self.database.get_setting(SELECTED_CHARACTER_SETTING)
        if selected not in CHARACTER_BY_ID:
            selected = DEFAULT_CHARACTER_ID
            self.database.set_setting(SELECTED_CHARACTER_SETTING, selected)
        return selected

    def get_selected(self):
        return CHARACTER_BY_ID[self.get_selected_id()]

    def select(self, character_id):
        if character_id not in CHARACTER_BY_ID:
            return False
        if character_id == self.get_selected_id():
            return False
        self.database.set_setting(SELECTED_CHARACTER_SETTING, character_id)
        return True

    def get_evolution_stage(self, level):
        return evolution_stage_for_level(level)
