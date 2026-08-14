"""Persistence across restarts: everything a user records must survive
closing and reopening the database connection, exactly as in v1.1.
"""

from Modules.activity import Activity


class TestRestartPersistence:
    def test_activities_survive_restart(self, tmp_path):
        from Database.database import Database

        path = tmp_path / "persist.db"

        first = Database(path)
        first.add_activity(
            Activity(
                id=None,
                date="2026-08-14",
                activity_type="Coding",
                name="Survives restart",
                estimated_minutes=45,
            )
        )
        first.close()

        second = Database(path)
        activities = second.get_activities_for_date("2026-08-14")
        assert len(activities) == 1
        assert activities[0].name == "Survives restart"
        assert activities[0].estimated_minutes == 45
        assert activities[0].original_estimate_minutes == 45
        second.close()

    def test_completed_activity_survives_restart(self, tmp_path, qapp):
        from Database.database import Database
        from Modules.session import SessionEngine

        path = tmp_path / "persist_complete.db"

        first = Database(path)
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Study",
            name="Done task",
            estimated_minutes=30,
        )
        first.add_activity(activity)
        loaded = first.get_activities_for_date("2026-08-14")[0]

        engine = SessionEngine(first)
        engine.start(loaded)
        engine.elapsed_seconds = 1805
        engine.complete()
        first.close()

        second = Database(path)
        refreshed = second.get_activities_for_date("2026-08-14")[0]
        assert refreshed.completed is True
        assert refreshed.actual_minutes == 31  # ceil(1805 / 60)
        assert refreshed.original_estimate_minutes == 30
        second.close()

    def test_xp_and_daily_history_survive_restart(self, tmp_path):
        from Database.database import Database

        path = tmp_path / "persist_xp.db"

        first = Database(path)
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Coding",
            name="XP task",
            estimated_minutes=60,
        )
        first.add_activity(activity)
        loaded = first.get_activities_for_date("2026-08-14")[0]
        loaded.completed = True
        loaded.actual_minutes = 75
        first.update_activity(loaded)
        total_xp = first.award_activity_completion_xp(loaded.id, 10)
        assert total_xp == 10
        first.close()

        second = Database(path)
        assert second.get_total_xp_setting() == 10
        history = second.get_daily_history()
        assert any(row[1] == "2026-08-14" for row in history)
        # Duplicate-XP protection still works after restart.
        again = second.award_activity_completion_xp(loaded.id, 10)
        assert again == 10
        second.close()
