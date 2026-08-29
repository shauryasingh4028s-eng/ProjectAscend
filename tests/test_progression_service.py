"""Unit tests for ProgressionService domain orchestration layer."""

from datetime import date
import pytest
from Database.database import Database
from Modules.xp_manager import XPManager
from Modules.streak_manager import StreakManager
from Modules.achievement_manager import AchievementManager
from Modules.character_manager import CharacterManager
from Modules.progression_service import ProgressionService
from Modules.activity import Activity


@pytest.fixture
def setup_progression(tmp_path):
    db_path = tmp_path / "test_progression.db"
    db = Database(db_path)
    db.set_daily_goal(60)

    xp_mgr = XPManager(db)
    streak_mgr = StreakManager(db)
    ach_mgr = AchievementManager(db, streak_mgr, xp_mgr)
    char_mgr = CharacterManager(db)

    prog_service = ProgressionService(
        db,
        xp_mgr,
        streak_mgr,
        ach_mgr,
        char_mgr,
    )
    return db, xp_mgr, streak_mgr, ach_mgr, char_mgr, prog_service


def test_progression_service_read_apis(setup_progression):
    db, xp_mgr, streak_mgr, ach_mgr, char_mgr, prog_service = setup_progression

    assert prog_service.get_total_xp() == 0
    assert prog_service.get_current_level() == 1

    lvl, xp_into, xp_for, xp_rem = prog_service.get_level_progress()
    assert lvl == 1
    assert xp_into == 0
    assert xp_for == 100
    assert xp_rem == 100

    evo = prog_service.get_evolution_stage()
    assert evo["stage"] == 1
    assert evo["name"] == "Initiated"

    char = prog_service.get_selected_character()
    assert char["id"] == "architect"


def test_progression_summary(setup_progression):
    db, xp_mgr, streak_mgr, ach_mgr, char_mgr, prog_service = setup_progression

    summary = prog_service.get_progression_summary()
    assert summary["total_xp"] == 0
    assert summary["level"] == 1
    assert summary["evolution_stage"] == 1
    assert summary["character"]["id"] == "architect"
    assert "current_streak" in summary
    assert "unlocked_achievements_count" in summary
    assert "milestones_reached_count" in summary


def test_check_progression_events_integration(setup_progression):
    db, xp_mgr, streak_mgr, ach_mgr, char_mgr, prog_service = setup_progression
    today = date.today().isoformat()

    # Complete 10 activities to accumulate 100 XP (Level 2 boundary)
    for i in range(10):
        act = Activity(None, today, "Coding", f"Task {i+1}", 15, completed=True, actual_minutes=15)
        db.add_activity(act)
        acts = db.get_activities_for_date(today)
        xp_mgr.award_activity_completion(acts[-1].id)

    report = prog_service.check_progression_events(trigger_event="test_event")

    assert report["total_xp"] == 100
    assert report["current_level"] == 2
    level_history = db.get_level_history()
    recorded_levels = {r["level"] if isinstance(r, dict) else r[0] for r in level_history}
    assert 2 in recorded_levels
    assert report["trigger_event"] == "test_event"


def test_retroactive_progression_reconciliation(setup_progression):
    db, xp_mgr, streak_mgr, ach_mgr, char_mgr, prog_service = setup_progression
    today = date.today().isoformat()

    # Add 100 completed activities with 6000 total focus minutes (100h focus)
    for i in range(100):
        act = Activity(None, today, "Coding", f"Task {i+1}", 60, completed=True, actual_minutes=60)
        db.add_activity(act)
        acts = db.get_activities_for_date(today)
        xp_mgr.award_activity_completion(acts[-1].id)

    # 100 completed activities = 1000 XP = Level 10 reached
    report = prog_service.check_progression_events(trigger_event="retroactive_test")

    assert report["total_xp"] == 1000
    assert report["current_level"] == 10
    assert report["evolution_stage"] == 2  # Stage 2 Established at Level 10

    # Verify achievements for level 10 and 100h deepwork unlocked
    unlocked_ids = ach_mgr.get_unlocked_ids()
    assert "mastery_level_10" in unlocked_ids
    assert "deepwork_100h" in unlocked_ids
