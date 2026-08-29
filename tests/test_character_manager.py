"""Unit tests for CharacterManager and Character Evolution Engine."""

import pytest
from Database.database import Database
from Modules.character_manager import CharacterManager, get_evolution_stage, CHARACTER_DEFINITIONS, DEFAULT_CHARACTER_ID


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_char.db"
    database = Database(db_path)
    return database


@pytest.fixture
def char_mgr(db):
    return CharacterManager(db)


def test_all_eight_characters_exist(char_mgr):
    characters = char_mgr.get_characters()
    assert len(characters) == 8
    char_ids = {c["id"] for c in characters}
    expected_ids = {"architect", "catalyst", "sentinel", "vanguard", "scholar", "pathfinder", "artisan", "paragon"}
    assert char_ids == expected_ids


def test_default_character_is_architect(char_mgr):
    selected_id = char_mgr.get_selected_character_id()
    assert selected_id == DEFAULT_CHARACTER_ID == "architect"
    selected = char_mgr.get_selected_character()
    assert selected["id"] == "architect"
    assert selected["name"] == "The Architect"


def test_valid_character_selection_persists(char_mgr, db, tmp_path):
    assert char_mgr.set_selected_character("catalyst") is True
    assert char_mgr.get_selected_character_id() == "catalyst"
    assert char_mgr.get_selected_character()["name"] == "The Catalyst"

    # Verify database persistence across manager re-instantiation
    new_char_mgr = CharacterManager(db)
    assert new_char_mgr.get_selected_character_id() == "catalyst"


def test_invalid_character_selection_rejected(char_mgr):
    assert char_mgr.set_selected_character("superman") is False
    assert char_mgr.get_selected_character_id() == "architect"
    assert char_mgr.get_selected_character()["id"] == "architect"


def test_evolution_stage_thresholds():
    # Level 1-9 -> Stage 1 Initiated
    st1 = get_evolution_stage(1)
    assert st1["stage"] == 1
    assert st1["name"] == "Initiated"
    assert st1["next_stage_level"] == 10

    st9 = get_evolution_stage(9)
    assert st9["stage"] == 1

    # Level 10-24 -> Stage 2 Established
    st10 = get_evolution_stage(10)
    assert st10["stage"] == 2
    assert st10["name"] == "Established"
    assert st10["next_stage_level"] == 25

    # Level 25-49 -> Stage 3 Ascended
    st25 = get_evolution_stage(25)
    assert st25["stage"] == 3
    assert st25["name"] == "Ascended"
    assert st25["next_stage_level"] == 50

    # Level 50+ -> Stage 4 Sovereign
    st50 = get_evolution_stage(50)
    assert st50["stage"] == 4
    assert st50["name"] == "Sovereign"
    assert st50["next_stage_level"] is None

    st100 = get_evolution_stage(100)
    assert st100["stage"] == 4


def test_asset_path_convention(char_mgr):
    path = char_mgr.get_character_asset_path("architect", stage=2)
    assert path == "assets/characters/architect/stage_2.png"

    path_inv = char_mgr.get_character_asset_path("invalid_id", stage=5)
    assert path_inv == "assets/characters/architect/stage_4.png"
