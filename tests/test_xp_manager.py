"""Tests for XPManager, XP Ledger Authoritativeness, and Idempotency Guarantees."""

import pytest
from datetime import date
from Database.database import Database
from Modules.activity import Activity
from Modules.xp_manager import XPManager


@pytest.fixture
def xp_setup(tmp_path):
    db_path = tmp_path / "xp_test.db"
    db = Database(str(db_path))
    xp_mgr = XPManager(db)
    yield db, xp_mgr
    db.close()


class TestXPManagerLedger:
    def test_initial_xp_is_zero(self, xp_setup):
        db, xp_mgr = xp_setup
        assert xp_mgr.get_total_xp() == 0
        assert db.get_total_xp_from_events() == 0
        assert db.get_setting("total_xp") == "0"

    def test_award_activity_completion_idempotency(self, xp_setup):
        db, xp_mgr = xp_setup
        today = date.today().isoformat()
        act = Activity(
            id=None,
            date=today,
            activity_type="Coding",
            name="Unit Test Task",
            estimated_minutes=30,
            completed=True,
        )
        db.add_activity(act)
        activities = db.get_activities_for_date(today)
        act_id = activities[0].id

        # First award: should grant +10 XP
        total_xp = xp_mgr.award_activity_completion(act_id)
        assert total_xp == 10
        assert db.get_total_xp_from_events() == 10

        # Repeated award for same activity: must NOT grant duplicate XP
        total_xp_again = xp_mgr.award_activity_completion(act_id)
        assert total_xp_again == 10
        assert db.get_total_xp_from_events() == 10

    def test_activity_uncompletion_void_event(self, xp_setup):
        db, xp_mgr = xp_setup
        today = date.today().isoformat()
        act = Activity(
            id=None,
            date=today,
            activity_type="Study",
            name="Void Test Task",
            estimated_minutes=45,
            completed=True,
        )
        db.add_activity(act)
        act_id = db.get_activities_for_date(today)[0].id

        # Complete and award
        xp_mgr.award_activity_completion(act_id)
        assert xp_mgr.get_total_xp() == 10

        # Mark activity uncompleted
        act_uncompleted = db.get_activities_for_date(today)[0]
        act_uncompleted.completed = False
        db.update_activity(act_uncompleted)

        # Total XP must decrease back to 0 via compensating void event
        assert xp_mgr.get_total_xp() == 0
        assert db.get_total_xp_from_events() == 0

        # Repeated uncompletion updates must NOT void repeatedly
        db.update_activity(act_uncompleted)
        assert xp_mgr.get_total_xp() == 0

    def test_activity_deletion_void_event(self, xp_setup):
        db, xp_mgr = xp_setup
        today = date.today().isoformat()
        act = Activity(
            id=None,
            date=today,
            activity_type="Study",
            name="Delete Void Task",
            estimated_minutes=20,
            completed=True,
        )
        db.add_activity(act)
        act_id = db.get_activities_for_date(today)[0].id

        # Complete and award
        xp_mgr.award_activity_completion(act_id)
        assert xp_mgr.get_total_xp() == 10

        # Delete activity
        db.delete_activity(act_id)
        assert xp_mgr.get_total_xp() == 0

    def test_daily_goal_xp_throttling(self, xp_setup):
        db, xp_mgr = xp_setup
        today = date.today().isoformat()

        # Without goal_completed == 1 in daily_history, daily goal XP must NOT be awarded
        assert xp_mgr.award_daily_goal(today) == 0

        # Add an activity that satisfies daily goal
        db.set_daily_goal(30)
        act = Activity(
            id=None,
            date=today,
            activity_type="Deep Work",
            name="Goal Activity",
            estimated_minutes=60,
            completed=True,
            actual_minutes=60,
        )
        db.add_activity(act)  # update_daily_history will set goal_completed = 1

        # Now award daily goal XP: should grant +50 XP
        total_xp = xp_mgr.award_daily_goal(today)
        assert total_xp >= 50

        # Repeated daily goal calls on same date must NOT grant duplicate XP
        xp_after_second_call = xp_mgr.award_daily_goal(today)
        assert xp_after_second_call == total_xp

    def test_cache_corruption_reconciliation(self, xp_setup):
        db, xp_mgr = xp_setup
        today = date.today().isoformat()
        act = Activity(
            id=None,
            date=today,
            activity_type="Coding",
            name="Task 1",
            estimated_minutes=15,
            completed=True,
        )
        db.add_activity(act)
        act_id = db.get_activities_for_date(today)[0].id
        xp_mgr.award_activity_completion(act_id)
        assert xp_mgr.get_total_xp() == 10

        # Deliberately corrupt settings.total_xp cache
        db.set_setting("total_xp", "9999")
        assert db.get_setting("total_xp") == "9999"

        # Reading through xp_mgr must reconcile settings.total_xp back to authoritative 10 XP
        reconciled_xp = xp_mgr.get_total_xp()
        assert reconciled_xp == 10
        assert db.get_setting("total_xp") == "10"
