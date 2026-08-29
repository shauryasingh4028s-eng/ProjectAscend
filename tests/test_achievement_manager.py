"""Unit tests for AchievementManager and Milestone System."""

from datetime import date
import pytest
from Database.database import Database
from Modules.xp_manager import XPManager
from Modules.streak_manager import StreakManager
from Modules.achievement_manager import AchievementManager, ACHIEVEMENT_DEFINITIONS, MILESTONE_CATALOG
from Modules.activity import Activity


@pytest.fixture
def setup_mgrs(tmp_path):
    db_path = tmp_path / "test_achieve.db"
    db = Database(db_path)
    db.set_daily_goal(60)
    xp_mgr = XPManager(db)
    streak_mgr = StreakManager(db)
    ach_mgr = AchievementManager(db, streak_mgr, xp_mgr)
    return db, xp_mgr, streak_mgr, ach_mgr


def test_achievement_triggers_and_persistence(setup_mgrs):
    db, xp_mgr, streak_mgr, ach_mgr = setup_mgrs
    today = date.today().isoformat()

    # Initial state: no achievements
    assert len(ach_mgr.get_unlocked_ids()) == 0

    # 1. Complete daily goal day (120 mins) -> consistency_first_step
    act = Activity(None, today, "Coding", "Goal Task", 120, completed=True, actual_minutes=120)
    db.add_activity(act)
    db.update_daily_history(today)
    newly_unlocked = ach_mgr.evaluate_achievements(trigger_event="daily_goal")
    unlocked_ids = ach_mgr.get_unlocked_ids()
    assert "consistency_first_step" in unlocked_ids
    assert any(a["id"] == "consistency_first_step" for a in newly_unlocked)

    # 2. Add 2 more completed activities (total 3) -> planning_perfect_day
    for i in range(2):
        act = Activity(None, today, "Coding", f"Task {i+2}", 30, completed=True, actual_minutes=30)
        db.add_activity(act)
        acts = db.get_activities_for_date(today)
        xp_mgr.award_activity_completion(acts[-1].id)

    ach_mgr.evaluate_achievements(trigger_event="tasks_completed")
    unlocked_ids = ach_mgr.get_unlocked_ids()
    assert "planning_perfect_day" in unlocked_ids


def test_achievement_idempotency_and_no_duplicate_rows(setup_mgrs):
    db, xp_mgr, streak_mgr, ach_mgr = setup_mgrs
    today = date.today().isoformat()
    act = Activity(None, today, "Coding", "Goal Task", 120, completed=True, actual_minutes=120)
    db.add_activity(act)
    db.update_daily_history(today)

    # Evaluate multiple times
    res1 = ach_mgr.evaluate_achievements()
    assert len(res1) > 0

    res2 = ach_mgr.evaluate_achievements()
    assert len(res2) == 0  # No new unlocks returned

    # Check database rows count
    unlocked_rows = db.get_unlocked_achievements()
    ids = [r["achievement_id"] if isinstance(r, dict) else r[0] for r in unlocked_rows]
    assert len(ids) == len(set(ids))  # No duplicate achievement IDs


def test_achievements_grant_zero_xp(setup_mgrs):
    db, xp_mgr, streak_mgr, ach_mgr = setup_mgrs
    today = date.today().isoformat()
    act = Activity(None, today, "Coding", "Goal Task", 60, completed=True, actual_minutes=60)
    db.add_activity(act)
    db.update_daily_history(today)

    xp_before = xp_mgr.get_total_xp()
    ach_mgr.evaluate_achievements()
    xp_after = xp_mgr.get_total_xp()

    assert xp_after == xp_before


def test_milestone_evaluation_and_retroactive_unlocks(setup_mgrs):
    db, xp_mgr, streak_mgr, ach_mgr = setup_mgrs
    today = date.today().isoformat()

    # Add 50 completed activities with 3000 total focus minutes (50h)
    for i in range(50):
        act = Activity(None, today, "Coding", f"Task {i}", 60, completed=True, actual_minutes=60)
        db.add_activity(act)

    new_milestones = ach_mgr.evaluate_milestones(trigger_event="retroactive_test")
    history = db.get_milestone_history()

    # Verify focus duration tier 1 (10h) and tier 2 (50h) were reached
    focus_tiers = {r["tier"] if isinstance(r, dict) else r[1] for r in history if (r["milestone_id"] if isinstance(r, dict) else r[0]) == "focus_duration"}
    assert 1 in focus_tiers
    assert 2 in focus_tiers

    # Verify completed_activities tier 1 (10) and tier 2 (50) were reached
    task_tiers = {r["tier"] if isinstance(r, dict) else r[1] for r in history if (r["milestone_id"] if isinstance(r, dict) else r[0]) == "completed_activities"}
    assert 1 in task_tiers
    assert 2 in task_tiers

    # Re-evaluation must be idempotent
    re_eval = ach_mgr.evaluate_milestones(trigger_event="idempotent_test")
    assert len(re_eval) == 0
