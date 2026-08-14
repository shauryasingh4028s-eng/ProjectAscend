"""Session completion persistence: the minute-level actual duration keeps
its exact v1.1 rounding semantics, precise elapsed seconds are preserved,
and the original planning estimate survives completion.
"""

from datetime import date

from Modules.activity import Activity
from Modules.session import SessionEngine


class TestSessionCompletion:
    def test_completion_writes_activity_and_focus_session(self, database, qapp):
        # The activity is planned for "today": record_focus_session stamps
        # the session's session_date with the machine's current date, so
        # anchoring the activity and the query window to today keeps the
        # test clock-independent on any machine.
        session_day = date.today().isoformat()

        activity = Activity(
            id=None,
            date=session_day,
            activity_type="Coding",
            name="Regression task",
            estimated_minutes=60,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date(session_day)[0]

        engine = SessionEngine(database)
        engine.start(loaded)
        engine.pause()                      # paused time must not count
        engine.resume()
        engine.elapsed_seconds = 3661       # 1h 1m 1s of real focus
        engine.complete()

        # The activity is completed with the v1.1 minute-rounding rule.
        refreshed = database.get_activities_for_date(session_day)[0]
        assert refreshed.completed is True
        assert refreshed.actual_minutes == 62  # ceil(3661 / 60)
        assert refreshed.original_estimate_minutes == 60

        # The focus session keeps the precise seconds and the minute value.
        records = database.get_insights_records(
            session_day, session_day
        )["focus_sessions"]
        assert len(records) == 1
        assert records[0]["actual_minutes"] == 62

        connection = database.connection
        seconds = connection.execute(
            "SELECT actual_seconds FROM focus_sessions WHERE activity_id = ?",
            (refreshed.id,),
        ).fetchone()[0]
        assert seconds == 3661

    def test_minute_rounding_matches_v1_1(self):
        engine = SessionEngine(database=None)
        # The established v1.1 behaviour: elapsed seconds round UP to whole
        # minutes. UI and analytics rely on this; it must not change.
        assert engine.convert_seconds_to_minutes(0) == 0
        assert engine.convert_seconds_to_minutes(1) == 1
        assert engine.convert_seconds_to_minutes(59) == 1
        assert engine.convert_seconds_to_minutes(60) == 1
        assert engine.convert_seconds_to_minutes(61) == 2
        assert engine.convert_seconds_to_minutes(3600) == 60

    def test_editing_estimate_after_completion_keeps_original(self, database, qapp):
        activity = Activity(
            id=None,
            date="2026-08-14",
            activity_type="Study",
            name="Revision",
            estimated_minutes=40,
        )
        database.add_activity(activity)
        loaded = database.get_activities_for_date("2026-08-14")[0]

        engine = SessionEngine(database)
        engine.start(loaded)
        engine.elapsed_seconds = 2400
        engine.complete()

        refreshed = database.get_activities_for_date("2026-08-14")[0]
        refreshed.estimated_minutes = 80
        database.update_activity(refreshed)

        final = database.get_activities_for_date("2026-08-14")[0]
        assert final.estimated_minutes == 80
        assert final.original_estimate_minutes == 40
