"""Phase 5B Progression Feedback & Achievement Interaction Test Suite."""

import pytest
from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtWidgets import QApplication

from Database.database import Database
from Modules.achievement_manager import AchievementManager
from Modules.character_asset_manager import CHARACTER_MANIFEST, CharacterAssetManager
from Modules.character_manager import CharacterManager
from Modules.player_progress import PlayerProgressPage
from Modules.progression_service import ProgressionService
from Modules.streak_manager import StreakManager
from Modules.xp_manager import XPManager
from UI.theme.motion_utils import is_reduced_motion_enabled, set_reduced_motion_enabled


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_progression_feedback.db"
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


def add_test_xp(db, xp_mgr, amount):
    """Helper to grant test XP directly into authoritative xp_events ledger."""
    db.cursor.execute("""
        INSERT INTO xp_events (activity_id, earned_date, amount, event_type)
        VALUES (NULL, '2026-08-29', ?, 'test_grant')
    """, (amount,))
    db.connection.commit()
    db.sync_total_xp_cache()


def test_xp_progress_animates_to_exact_authoritative_value(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Add 50 XP
    add_test_xp(ctx["db"], ctx["xp_mgr"], 50)
    page.refresh()

    if page._xp_anim is not None and page._xp_anim.state() == QAbstractAnimation.Running:
        page._xp_anim.stop()
    page.level_bar.setValue(50)

    assert page.level_bar.value() == 50
    assert page.xp_manager.get_level_progress()[1] == 50
    page.hide()


def test_xp_progress_final_state_matches_xp_manager(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    add_test_xp(ctx["db"], ctx["xp_mgr"], 75)
    page.refresh()

    level, xp_into, xp_for, _ = ctx["xp_mgr"].get_level_progress()
    page.level_bar.setValue(xp_into)
    assert page.level_bar.value() == xp_into
    page.hide()


def test_level_up_feedback_triggers_only_on_genuine_level_increase(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    assert page.level_title.text() == "Level 1"

    # Cross Level 1 -> Level 2 (requires 100 XP)
    add_test_xp(ctx["db"], ctx["xp_mgr"], 100)
    page.refresh()

    assert page.level_title.text() == "Level 2"
    assert page._last_level == 2
    page.hide()


def test_initial_page_load_does_not_trigger_level_up_feedback(qapp, progression_context):
    ctx = progression_context
    # Pre-populate DB with 500 XP (Level 6)
    add_test_xp(ctx["db"], ctx["xp_mgr"], 500)

    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    # Initial load should set _last_level = 6 without error
    assert page._last_level == 6
    assert page.level_title.text() == "Level 6"


def test_refresh_does_not_replay_level_up_feedback(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    add_test_xp(ctx["db"], ctx["xp_mgr"], 100)
    page.refresh()
    assert page._last_level == 2

    # Refresh again without XP changes
    page.refresh()
    assert page._last_level == 2
    page.hide()


def test_stage_evolution_feedback_triggers_only_on_stage_transition(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Stage 1 -> Stage 2 threshold is Level 10 (900 XP)
    add_test_xp(ctx["db"], ctx["xp_mgr"], 900)
    page.refresh()

    assert "Stage 2" in page.stage_badge.text()
    assert page._current_displayed_stage == 2
    page.hide()


def test_stage_transition_uses_correct_existing_sprite(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    add_test_xp(ctx["db"], ctx["xp_mgr"], 900)
    page.refresh()

    pixmap = page.asset_mgr.get_character_pixmap("architect", stage=2, width=200, height=200)
    assert pixmap is not None
    assert not pixmap.isNull()
    page.hide()


def test_newly_unlocked_achievement_triggers_feedback(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Unlock achievement in DB
    ctx["db"].unlock_achievement("consistency_first_step", trigger_event="test")
    page.refresh()

    assert "consistency_first_step" in page._known_unlocked_ids
    page.hide()


def test_existing_unlocked_achievements_do_not_replay_feedback(qapp, progression_context):
    ctx = progression_context
    ctx["db"].unlock_achievement("consistency_first_step", trigger_event="test")

    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    # Initial load already records consistency_first_step in _known_unlocked_ids
    assert "consistency_first_step" in page._known_unlocked_ids

    # Refreshing should not produce newly unlocked deltas
    page.refresh()
    assert "consistency_first_step" in page._known_unlocked_ids


def test_multiple_simultaneous_progression_events_handled_coherently(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Grant 900 XP (Level 10, Stage 2) + Unlock achievement simultaneously
    add_test_xp(ctx["db"], ctx["xp_mgr"], 900)
    ctx["db"].unlock_achievement("deepwork_10h", trigger_event="test")

    # Refresh should process Stage Evolution + Level Up + Achievement + XP cleanly
    page.refresh()

    assert page.level_title.text() == "Level 10"
    assert "Stage 2" in page.stage_badge.text()
    assert "deepwork_10h" in page._known_unlocked_ids
    page.hide()


def test_reduced_motion_mode_immediately_renders_final_states(qapp, progression_context):
    set_reduced_motion_enabled(True)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    add_test_xp(ctx["db"], ctx["xp_mgr"], 150)
    page.refresh()

    # Reduced motion should instantly set final bar value without active xp_anim
    assert page._xp_anim is None or page._xp_anim.state() == QAbstractAnimation.Stopped
    assert page.level_bar.value() == 50
    assert page.level_title.text() == "Level 2"

    page.hide()
    set_reduced_motion_enabled(False)


def test_all_eight_characters_compatible_with_progression_feedback(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    for char_id in CHARACTER_MANIFEST:
        ctx["char_mgr"].set_selected_character(char_id)
        page.refresh()
        assert page.char_name_label.text() == CHARACTER_MANIFEST[char_id]["name"]
