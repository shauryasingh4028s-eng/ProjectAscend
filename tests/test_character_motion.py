"""Phase 5A Character Motion & Presentation Layer Test Suite."""

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
    db_file = tmp_path / "test_character_motion.db"
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


def test_idle_animation_starts_safely(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    page.start_idle_animation()
    assert page._idle_anim is not None
    assert page._idle_anim.state() == QAbstractAnimation.Running
    page.hide()


def test_idle_animation_stops_safely(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()
    page.start_idle_animation()
    assert page._idle_anim.state() == QAbstractAnimation.Running

    page.stop_idle_animation()
    assert page._idle_anim.state() == QAbstractAnimation.Stopped
    page.hide()


def test_stopping_idle_motion_restores_neutral_position(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()
    page.start_idle_animation()
    page._on_idle_anim_frame(0.25)  # Shifts offset to -3 (y=5)

    assert page.avatar_label.y() != PlayerProgressPage.NEUTRAL_Y

    page.stop_idle_animation()
    assert page.avatar_label.y() == PlayerProgressPage.NEUTRAL_Y
    page.hide()


def test_repeated_show_hide_cycles_no_duplicates(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    idle_anim_instances = set()
    for _ in range(5):
        page.show()
        if page._idle_anim is not None:
            idle_anim_instances.add(id(page._idle_anim))
        page.hide()

    # Verify that at most one QVariantAnimation controller was instantiated & reused
    assert len(idle_anim_instances) <= 1


def test_character_switching_updates_displayed_sprite(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    ctx["char_mgr"].set_selected_character("catalyst")
    page._on_character_changed("catalyst")

    assert page.char_name_label.text() == "The Catalyst"
    assert ctx["char_mgr"].get_selected_character_id() == "catalyst"
    page.hide()


def test_character_switching_preserves_selection_state(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    for char_id in ["vanguard", "sentinel", "scholar", "architect"]:
        ctx["char_mgr"].set_selected_character(char_id)
        page.refresh()
        assert ctx["char_mgr"].get_selected_character_id() == char_id
        assert page.progression_service.get_progression_summary()["character"]["id"] == char_id


def test_rapid_character_switching_safety(qapp, progression_context):
    set_reduced_motion_enabled(False)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    # Rapidly switch character identity across multiple archetypes
    sequence = ["architect", "catalyst", "sentinel", "vanguard", "scholar"]
    for char_id in sequence:
        ctx["char_mgr"].set_selected_character(char_id)
        page.refresh()

    # Process events to allow mid-frame calculations to finish
    QApplication.processEvents()

    # Fast forward switch animation to end
    if page._switch_anim is not None and page._switch_anim.state() == QAbstractAnimation.Running:
        page._switch_anim.stop()

    page.refresh()

    assert ctx["char_mgr"].get_selected_character_id() == "scholar"
    assert page.char_name_label.text() == "The Scholar"
    assert page._current_displayed_char_id == "scholar"
    page.hide()


def test_reduced_motion_disables_idle_animation(qapp, progression_context):
    set_reduced_motion_enabled(True)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    page.start_idle_animation()
    assert page._idle_anim is None or page._idle_anim.state() == QAbstractAnimation.Stopped
    assert page.avatar_label.y() == PlayerProgressPage.NEUTRAL_Y

    page.hide()
    set_reduced_motion_enabled(False)


def test_reduced_motion_skips_switch_transition(qapp, progression_context):
    set_reduced_motion_enabled(True)
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.show()

    ctx["char_mgr"].set_selected_character("paragon")
    page.refresh()

    # Switch animation should not be instantiated or running
    assert page._switch_anim is None or page._switch_anim.state() == QAbstractAnimation.Stopped
    assert page._current_displayed_char_id == "paragon"
    assert page.avatar_label.y() == PlayerProgressPage.NEUTRAL_Y

    page.hide()
    set_reduced_motion_enabled(False)


def test_all_8_characters_and_4_stages_motion_readiness(qapp, progression_context):
    asset_mgr = CharacterAssetManager()
    for char_id in CHARACTER_MANIFEST:
        for stage in range(1, 5):
            pixmap = asset_mgr.get_character_pixmap(char_id, stage=stage, width=200, height=200)
            assert pixmap is not None
            assert not pixmap.isNull()
            assert pixmap.width() > 0 and pixmap.height() > 0
            assert pixmap.width() <= 200 and pixmap.height() <= 200
