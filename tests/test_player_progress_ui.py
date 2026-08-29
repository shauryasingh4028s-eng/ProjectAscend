"""UI & Component Integration tests for Player Progress Phase 3."""

import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from Database.database import Database
from Dialogs.achievement_library_dialog import AchievementLibraryDialog
from Dialogs.character_selector_dialog import CharacterSelectorDialog
from Modules.achievement_manager import AchievementManager
from Modules.character_manager import CharacterManager
from Modules.player_progress import PlayerProgressPage
from Modules.progression_service import ProgressionService
from Modules.streak_manager import StreakManager
from Modules.xp_manager import XPManager
from UI.theme.design_system import ThemeManager


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_progress_ui.db"
    db = Database(str(db_file))
    yield db
    db.close()


@pytest.fixture
def progression_context(temp_db):
    xp_mgr = XPManager(temp_db)
    streak_mgr = StreakManager(temp_db)
    ach_mgr = AchievementManager(temp_db, streak_mgr, xp_mgr)
    char_mgr = CharacterManager(temp_db)
    prog_svc = ProgressionService(temp_db, xp_mgr, streak_mgr, ach_mgr, char_mgr)
    return {
        "db": temp_db,
        "xp_mgr": xp_mgr,
        "streak_mgr": streak_mgr,
        "ach_mgr": ach_mgr,
        "char_mgr": char_mgr,
        "prog_svc": prog_svc,
    }


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_player_progress_page_build_and_refresh(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    assert page.char_name_label.text() == "The Architect"
    assert "Stage 1" in page.stage_badge.text()
    assert page.level_title.text() == "Level 1"

    # Verify 4 macro milestone cards exist
    assert "focus_duration" in page.milestone_cards
    assert "completed_activities" in page.milestone_cards
    assert "daily_goal_days" in page.milestone_cards
    assert "longest_streak" in page.milestone_cards


def test_character_selection_persistence_ui(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    # Change character via character manager
    ctx["char_mgr"].set_selected_character("catalyst")
    page.refresh()

    assert page.char_name_label.text() == "The Catalyst"
    assert page.char_identity_label.text() == "Execution & Speed Mastery"
    assert ctx["char_mgr"].get_selected_character_id() == "catalyst"


def test_character_selector_dialog_creation(qapp, progression_context):
    ctx = progression_context
    dialog = CharacterSelectorDialog(ctx["char_mgr"], current_level=12)

    assert dialog.windowTitle() == "Select Identity Archetype"

    # Test selection signal
    dialog.select_character("vanguard")
    assert ctx["char_mgr"].get_selected_character_id() == "vanguard"


def test_achievement_library_dialog(qapp, progression_context):
    ctx = progression_context
    dialog = AchievementLibraryDialog(ctx["ach_mgr"])

    assert dialog.windowTitle() == "Achievement Library"
    assert dialog.active_category == "All"

    # Test filtering categories
    dialog.filter_category("Consistency")
    assert dialog.active_category == "Consistency"

    dialog.filter_category("Deep Work")
    assert dialog.active_category == "Deep Work"


def test_milestones_card_tier_scaling(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    # Simulate 600 minutes focus time (10 hours)
    card = page.milestone_cards["focus_duration"]
    card.update_data(600, "focus_duration")
    assert card.val_label.text() == "10h 0m"
    assert "Tier 1" in card.tier_badge.text()

    # Simulate 36,000 minutes focus time (600 hours -> surpasses Tier 5 of 500 hours)
    card.update_data(36000, "focus_duration")
    assert "Tier 5 (Max)" in card.tier_badge.text()
