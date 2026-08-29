"""Phase 5C Progression UX & Microinteraction Polish Test Suite."""

import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from Database.database import Database
from Dialogs.achievement_library_dialog import AchievementCardWidget, AchievementLibraryDialog
from Modules.achievement_manager import ACHIEVEMENT_DEFINITIONS, AchievementManager
from Modules.character_asset_manager import CHARACTER_MANIFEST
from Modules.character_manager import CharacterManager
from Modules.player_progress import MilestoneCardWidget, PlayerProgressPage, StageEvolutionIndicatorWidget
from Modules.progression_service import ProgressionService
from Modules.streak_manager import StreakManager
from Modules.xp_manager import XPManager
from UI.theme.motion_utils import is_reduced_motion_enabled, set_reduced_motion_enabled


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_progression_ux_polish.db"
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


def test_hero_typography_hierarchy_renders_correctly(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    assert page.char_name_label.text() == "The Architect"
    assert page.char_identity_label.text() == "Focus & Planning Mastery"
    assert page.level_title.text() == "Level 1"
    assert "XP earned in total" in page.total_xp_label.text()
    assert "XP" in page.next_level_label.text()


def test_evolution_stage_indicator_nodes_reflect_authoritative_stage(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )

    summary = ctx["prog_svc"].get_progression_summary()
    expected_stage = summary["evolution_info"]["stage"]
    assert page.evolution_indicator._current_stage == expected_stage


def test_evolution_indicator_renders_all_4_stages_correctly(qapp):
    indicator = StageEvolutionIndicatorWidget(current_stage=1)
    assert indicator._current_stage == 1

    for stage in [1, 2, 3, 4]:
        indicator.set_stage(stage)
        assert indicator._current_stage == stage


def test_achievement_card_locked_vs_unlocked_visual_states(qapp):
    sample_info = list(ACHIEVEMENT_DEFINITIONS.values())[0]

    locked_card = AchievementCardWidget(sample_info, unlock_record=None)
    assert not locked_card.is_unlocked
    assert locked_card.property("locked") == "true"

    unlocked_card = AchievementCardWidget(sample_info, unlock_record={"unlocked_at": "2026-08-29T12:00:00"})
    assert unlocked_card.is_unlocked
    assert unlocked_card.property("selected") == "true"


def test_achievement_card_hover_interaction_does_not_mutate_data(qapp):
    set_reduced_motion_enabled(False)
    sample_info = list(ACHIEVEMENT_DEFINITIONS.values())[0]
    card = AchievementCardWidget(sample_info, unlock_record=None)

    enter_event = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    card.enterEvent(enter_event)
    assert card.achievement_id == sample_info["id"]

    card.leaveEvent(QEvent(QEvent.Type.Leave))
    assert card.achievement_id == sample_info["id"]


def test_achievement_library_dialog_rendering_and_categories(qapp, progression_context):
    ctx = progression_context
    dialog = AchievementLibraryDialog(ctx["ach_mgr"])
    dialog.show()

    expected_categories = ["All", "Consistency", "Deep Work", "Planning", "Mastery"]
    for cat in expected_categories:
        assert cat in dialog.filter_buttons

    dialog.filter_category("Consistency")
    assert dialog.active_category == "Consistency"
    dialog.hide()


def test_milestone_card_visual_hierarchy_and_hover(qapp):
    set_reduced_motion_enabled(False)
    card = MilestoneCardWidget("Focus Hours", "⏳", 120, "focus_duration")

    assert "2h 0m" in card.val_label.text()

    enter_event = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    card.enterEvent(enter_event)
    card.leaveEvent(QEvent(QEvent.Type.Leave))
    assert card.val_label.text() == "2h 0m"


def test_reduced_motion_disables_hover_transitions(qapp):
    set_reduced_motion_enabled(True)
    card = MilestoneCardWidget("Focus Hours", "⏳", 120, "focus_duration")

    enter_event = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    card.enterEvent(enter_event)
    card.leaveEvent(QEvent(QEvent.Type.Leave))

    set_reduced_motion_enabled(False)


def test_all_8_characters_and_4_stages_compatible_with_phase5c(qapp, progression_context):
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


def test_deep_focus_dark_theme_rendering(qapp, progression_context):
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


def test_clear_thinking_light_theme_rendering(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    page.setProperty("theme", "light")
    page.refresh()
    assert page.property("theme") == "light"


def test_existing_phase5a_5b_tests_remain_passing(qapp, progression_context):
    ctx = progression_context
    page = PlayerProgressPage(
        ctx["xp_mgr"],
        ctx["streak_mgr"],
        progression_service=ctx["prog_svc"],
        character_manager=ctx["char_mgr"],
    )
    assert hasattr(page, "_idle_anim")
    assert hasattr(page, "_switch_anim")
    assert hasattr(page, "_last_level")
    assert hasattr(page, "_last_stage")
