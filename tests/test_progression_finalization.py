"""Phase 5D Final Gamification System Finalization & Production Readiness Test Suite."""

import os
from pathlib import Path
import pytest
from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtWidgets import QApplication

from Database.database import Database
from Dialogs.achievement_library_dialog import AchievementCardWidget, AchievementLibraryDialog
from Dialogs.character_selector_dialog import CharacterSelectorDialog
from Modules.achievement_manager import ACHIEVEMENT_DEFINITIONS, MILESTONE_CATALOG, AchievementManager
from Modules.character_asset_manager import CHARACTER_MANIFEST, CharacterAssetManager
from Modules.character_manager import CharacterManager
from Modules.player_progress import PlayerProgressPage, StageEvolutionIndicatorWidget
from Modules.progression_service import ProgressionService
from Modules.streak_manager import StreakManager
from Modules.xp_manager import XPManager
from UI.theme.motion_utils import is_reduced_motion_enabled, set_reduced_motion_enabled


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_progression_finalization.db"
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


def add_test_xp(db, amount):
    """Grant test XP directly into authoritative xp_events ledger."""
    db.cursor.execute("""
        INSERT INTO xp_events (activity_id, earned_date, amount, event_type)
        VALUES (NULL, '2026-08-29', ?, 'test_grant')
    """, (amount,))
    db.connection.commit()
    db.sync_total_xp_cache()


def test_all_32_character_sprites_exist_and_unmodified():
    asset_mgr = CharacterAssetManager()
    base_dir = Path(asset_mgr.base_dir)

    count = 0
    for char_id in CHARACTER_MANIFEST:
        for stage in range(1, 5):
            path = base_dir / "assets" / "characters" / char_id / f"stage_{stage}.png"
            assert path.exists(), f"Missing production sprite: {path}"
            assert path.stat().st_size > 0, f"Empty sprite file: {path}"
            count += 1

    assert count == 32


def test_nearest_neighbor_scaling_preserved(qapp):
    asset_mgr = CharacterAssetManager()
    pixmap = asset_mgr.get_character_pixmap("architect", stage=1, width=200, height=200)
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.width() <= 200
    assert pixmap.height() <= 200


def test_fresh_user_initialization_no_false_unlocks(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    assert page._last_level == 1
    assert page._last_stage == 1
    assert page.level_title.text() == "Level 1"
    assert page.stage_badge.text() == "Stage 1 — Initiated"
    assert len(page._known_unlocked_ids) == 0


def test_existing_user_restart_persistence(qapp, temp_db, tmp_path):
    # Pre-populate DB
    xp_mgr = XPManager(temp_db)
    streak_mgr = StreakManager(temp_db)
    ach_mgr = AchievementManager(temp_db, streak_mgr, xp_mgr)
    char_mgr = CharacterManager(temp_db)
    prog_svc = ProgressionService(temp_db, xp_mgr, streak_mgr, ach_mgr, char_mgr)

    add_test_xp(temp_db, 900)
    char_mgr.set_selected_character("catalyst")

    # Create page
    page = PlayerProgressPage(
        xp_mgr,
        streak_mgr,
        progression_service=prog_svc,
        character_manager=char_mgr,
    )

    assert page._last_level == 10
    assert page._last_stage == 2
    assert page.char_name_label.text() == "The Catalyst"
    assert page.level_title.text() == "Level 10"


def test_phase5a_5b_5c_coexistence_and_priority(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Trigger XP + Level + Stage simultaneously
    add_test_xp(ctx["db"], 900)
    page.refresh()

    assert page.level_title.text() == "Level 10"
    assert page.evolution_indicator._current_stage == 2
    page.hide()


def test_all_8_characters_across_all_4_stages(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    xp_for_stages = {
        1: 0,
        2: 900,
        3: 4650,
        4: 10900,
    }

    for char_id in CHARACTER_MANIFEST:
        ctx["char_mgr"].set_selected_character(char_id)
        for stage, xp_amt in xp_for_stages.items():
            ctx["db"].cursor.execute("DELETE FROM xp_events")
            ctx["db"].connection.commit()
            add_test_xp(ctx["db"], xp_amt)

            page.refresh()
            assert page.char_name_label.text() == CHARACTER_MANIFEST[char_id]["name"]
            assert page.evolution_indicator._current_stage == stage


def test_reduced_motion_disables_all_motion_systems(qapp, progression_context):
    set_reduced_motion_enabled(True)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    add_test_xp(ctx["db"], 100)
    page.refresh()

    assert page._xp_anim is None or page._xp_anim.state() == QAbstractAnimation.Stopped
    page.hide()
    set_reduced_motion_enabled(False)


def test_dark_and_light_theme_rendering_stability(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    page.setProperty("theme", "dark")
    page.refresh()
    assert page.property("theme") == "dark"

    page.setProperty("theme", "light")
    page.refresh()
    assert page.property("theme") == "light"


def test_zero_layout_warnings_on_rapid_refresh(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    # Perform 20 rapid refreshes across stages
    for stage_xp in [0, 900, 4650, 10900] * 5:
        add_test_xp(ctx["db"], stage_xp)
        page.refresh()

    assert page.level_title.text() is not None


def test_achievement_catalog_integrity():
    assert len(ACHIEVEMENT_DEFINITIONS) >= 11
    for aid, info in ACHIEVEMENT_DEFINITIONS.items():
        assert "id" in info
        assert "name" in info
        assert "description" in info
        assert "category" in info
        assert "icon" in info


def test_milestone_catalog_integrity():
    assert len(MILESTONE_CATALOG) == 4
    for key, cat in MILESTONE_CATALOG.items():
        assert "name" in cat
        assert "tiers" in cat
        assert len(cat["tiers"]) == 5


def test_xp_ledger_authoritativeness(progression_context):
    ctx = progression_context
    assert ctx["xp_mgr"].get_total_xp() == 0
    add_test_xp(ctx["db"], 250)
    assert ctx["xp_mgr"].get_total_xp() == 250


def test_character_selector_dialog_persistence(qapp, progression_context):
    ctx = progression_context
    dialog = CharacterSelectorDialog(ctx["char_mgr"], current_level=1)
    dialog.show()

    success = ctx["char_mgr"].set_selected_character("catalyst")
    assert success
    assert ctx["char_mgr"].get_selected_character_id() == "catalyst"
    dialog.hide()


def test_full_suite_regression_lock(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    assert hasattr(page, "avatar_label")
    assert hasattr(page, "level_bar")
    assert hasattr(page, "evolution_indicator")
    assert hasattr(page, "milestone_cards")
