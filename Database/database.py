from pathlib import Path
from Modules.activity import Activity
from datetime import date
import sqlite3
import os

# The schema version this build maintains. SQLite's ``user_version`` pragma
# stores the version of an existing database file, and MIGRATIONS brings old
# files forward in version order. Bump SCHEMA_VERSION and add a migration
# whenever the schema changes.
#
# v1  - v1.1 baseline schema (activities, settings, focus_sessions,
#       xp_events, daily_history).
# v2  - v1.2 Calibration Foundation:
#       * activities.original_estimate_minutes preserves the ORIGINAL
#         planning estimate after the editable estimate is changed.
#       * focus_sessions.actual_seconds keeps the precise elapsed execution
#         seconds while the existing minute-level fields stay unchanged.
SCHEMA_VERSION = 2


def _has_column(cursor, table, column):
    # Return True when the table already has the named column.
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _migrate_to_v2(cursor):
    """v1.2 Calibration Foundation.

    - Preserve the original planning estimate separately from the editable
      estimate, so calibration compares the original plan against the actual
      result even when the user later edits the estimate.
    - Keep precise elapsed seconds for future analytics. Existing
      minute-level columns and their meanings are unchanged.

    Existing rows cannot recover a previously edited original estimate, so
    they are backfilled from their current estimate - the best available
    value. This migration is idempotent and safe to re-run.
    """
    if not _has_column(cursor, "activities", "original_estimate_minutes"):
        cursor.execute(
            "ALTER TABLE activities ADD COLUMN "
            "original_estimate_minutes INTEGER NOT NULL DEFAULT 0"
        )

    cursor.execute(
        "UPDATE activities "
        "SET original_estimate_minutes = estimated_minutes "
        "WHERE original_estimate_minutes = 0 AND estimated_minutes > 0"
    )

    if not _has_column(cursor, "focus_sessions", "actual_seconds"):
        cursor.execute(
            "ALTER TABLE focus_sessions ADD COLUMN actual_seconds INTEGER"
        )


# Ordered schema migrations: target version -> migration callable.
MIGRATIONS = {
    2: _migrate_to_v2,
}


class Database:
    def __init__(self, database_path=None):
        # Store the database in the user's AppData folder.
        if database_path is None:
            database_folder = (
                Path(os.getenv("LOCALAPPDATA"))
                / "ProjectAscend"
                / "Database"
            )
            database_folder.mkdir(parents=True, exist_ok=True)
            database_path = database_folder / "ascend.db"
        else:
            database_path = Path(database_path)
            database_path.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(database_path)
        self.cursor = self.connection.cursor()

        self.create_tables()

    def create_tables(self):
        # Create the activities table for permanent activity storage.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                estimated_minutes INTEGER NOT NULL,
                original_estimate_minutes INTEGER NOT NULL DEFAULT 0,
                completed INTEGER DEFAULT 0,
                actual_minutes INTEGER DEFAULT 0,
                xp_awarded INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Create the settings table for simple permanent app settings.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Save timestamped focus sessions for time-of-day Insights patterns.
        # Activity.actual_minutes remains the canonical source for completed
        # activity focus totals, which preserves all existing history.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                session_date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                actual_minutes INTEGER NOT NULL DEFAULT 0,
                actual_seconds INTEGER
            )
        """)

        # Store award events so range-based XP is based on real, historical
        # rewards rather than attempting to infer them from the current total.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS xp_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                earned_date TEXT NOT NULL,
                amount INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                UNIQUE(activity_id, event_type)
            )
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_focus_sessions_date
            ON focus_sessions(session_date)
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_xp_events_date
            ON xp_events(earned_date)
        """)

        # Create the daily history table for saved daily summaries.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                study_minutes INTEGER NOT NULL DEFAULT 0,
                completed_activities INTEGER NOT NULL DEFAULT 0,
                total_activities INTEGER NOT NULL DEFAULT 0,
                goal_completed INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Add newer activity columns if this database is from an older version.
        self.add_missing_columns()

        # Reconstruct analytics-only history for the fixed completion reward
        # already represented by completed activity records. This never changes
        # total XP or awards an activity a second time.
        self.backfill_activity_completion_xp_events()

        # Insert the default daily goal if it does not already exist.
        self.create_default_settings()

        # Bring older database files forward to the current schema version.
        self.run_migrations()

        # Save table and default-setting changes to the SQLite database file.
        self.connection.commit()

    def get_schema_version(self):
        # Return the schema version stored in the database file.
        self.cursor.execute("PRAGMA user_version")
        row = self.cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def run_migrations(self):
        # Apply pending migrations in version order and record each completed
        # version immediately. Every migration is idempotent, so an
        # interrupted upgrade simply finishes the remaining steps on the next
        # start without duplicating work or data.
        current_version = self.get_schema_version()

        if current_version > SCHEMA_VERSION:
            # The file was written by a newer build. Leave it untouched.
            return

        for target_version in sorted(MIGRATIONS):
            if target_version <= current_version:
                continue
            MIGRATIONS[target_version](self.cursor)
            current_version = target_version
            self.cursor.execute(f"PRAGMA user_version = {target_version}")

    def add_missing_columns(self):
        # Read the current column names from the activities table.
        self.cursor.execute("PRAGMA table_info(activities)")
        columns = self.cursor.fetchall()
        column_names = []

        for column in columns:
            column_names.append(column[1])

        # Older databases may not have a date column yet.
        if "date" not in column_names:
            self.cursor.execute(
                "ALTER TABLE activities ADD COLUMN date TEXT DEFAULT ''"
            )

        # Older databases may not have an actual_minutes column yet.
        if "actual_minutes" not in column_names:
            self.cursor.execute(
                "ALTER TABLE activities "
                "ADD COLUMN actual_minutes INTEGER DEFAULT 0"
            )

        # Track whether an activity's completion XP was already awarded.
        if "xp_awarded" not in column_names:
            self.cursor.execute(
                "ALTER TABLE activities "
                "ADD COLUMN xp_awarded INTEGER NOT NULL DEFAULT 0"
            )

    def create_default_settings(self):
        # Add the default daily goal only when it does not already exist.
        if self.get_setting("daily_goal") is None:
            self.set_setting("daily_goal", "360")

    def backfill_activity_completion_xp_events(self):
        # Every activity marked xp_awarded received the established 10 XP
        # completion reward. Existing installations predate xp_events, so
        # record those known rewards for Insights without modifying total XP.
        self.cursor.execute("""
            INSERT OR IGNORE INTO xp_events (
                activity_id,
                earned_date,
                amount,
                event_type
            )
            SELECT id, date, 10, 'activity_completion'
            FROM activities
            WHERE completed = 1
              AND xp_awarded = 1
        """)

    def add_activity(self, activity):
        # Save one Activity object permanently into SQLite.
        self.cursor.execute("""
            INSERT INTO activities (
                date,
                activity_type,
                name,
                estimated_minutes,
                original_estimate_minutes,
                completed,
                actual_minutes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            activity.date,
            activity.activity_type,
            activity.name,
            activity.estimated_minutes,
            activity.original_estimate_minutes or activity.estimated_minutes,
            int(activity.completed),
            activity.actual_minutes,
        ))

        # Commit makes the activity stay saved after closing the app.
        self.connection.commit()

        # Keep the daily history summary synchronized automatically.
        self.update_daily_history(activity.date)

    def get_activities(self):
        # Read every saved activity from SQLite.
        self.cursor.execute("""
            SELECT
                id,
                date,
                activity_type,
                name,
                estimated_minutes,
                original_estimate_minutes,
                completed,
                actual_minutes
            FROM activities
            ORDER BY id
        """)

        return self.rows_to_activities(self.cursor.fetchall())

    def get_activities_for_date(self, activity_date):
        # Read only the activities that belong to one selected date.
        self.cursor.execute("""
            SELECT
                id,
                date,
                activity_type,
                name,
                estimated_minutes,
                original_estimate_minutes,
                completed,
                actual_minutes
            FROM activities
            WHERE date = ?
            ORDER BY id
        """, (activity_date,))

        return self.rows_to_activities(self.cursor.fetchall())

    def update_activity(self, activity):
        # Update an existing activity using its database id.
        self.cursor.execute("""
            UPDATE activities
            SET
                date = ?,
                activity_type = ?,
                name = ?,
                estimated_minutes = ?,
                completed = ?,
                actual_minutes = ?
            WHERE id = ?
        """, (
            activity.date,
            activity.activity_type,
            activity.name,
            activity.estimated_minutes,
            int(activity.completed),
            activity.actual_minutes,
            activity.id,
        ))

        # Preserve the ORIGINAL planning estimate. Calibration must compare
        # the plan that existed before execution against the actual result,
        # so once an activity has recorded work (a focus session or a
        # completion), later estimate edits no longer change the original.
        # Before any work is recorded, an edit is still part of planning and
        # updates the original too.
        self.cursor.execute("""
            UPDATE activities
            SET original_estimate_minutes = ?
            WHERE id = ?
              AND completed = 0
              AND NOT EXISTS (
                  SELECT 1 FROM focus_sessions
                  WHERE focus_sessions.activity_id = activities.id
              )
        """, (
            activity.estimated_minutes,
            activity.id,
        ))

        # Save the update permanently.
        self.connection.commit()

        # Keep the daily history summary synchronized automatically.
        self.update_daily_history(activity.date)

    def delete_activity(self, activity_id):
        # Find the activity date before deleting the row.
        self.cursor.execute("""
            SELECT date
            FROM activities
            WHERE id = ?
        """, (activity_id,))

        row = self.cursor.fetchone()

        if row is None:
            return

        activity_date = row[0]

        # Delete one activity from SQLite by its id.
        self.cursor.execute("""
            DELETE FROM activities
            WHERE id = ?
        """, (activity_id,))

        # Save the deletion permanently.
        self.connection.commit()

        # Keep the daily history summary synchronized automatically.
        self.update_daily_history(activity_date)

    def rows_to_activities(self, rows):
        # Convert SQLite rows into Activity objects used by the app.
        activities = []

        for row in rows:
            activity = Activity(
                id=row[0],
                date=row[1],
                activity_type=row[2],
                name=row[3],
                estimated_minutes=row[4],
                original_estimate_minutes=row[5],
                completed=bool(row[6]),
                actual_minutes=row[7],
            )
            activities.append(activity)

        return activities

    def get_setting(self, key):
        # Return one setting value, or None if the key does not exist.
        self.cursor.execute("""
            SELECT value
            FROM settings
            WHERE key = ?
        """, (key,))

        row = self.cursor.fetchone()

        if row is None:
            return None

        return row[0]

    def set_setting(self, key, value):
        # Insert a new setting or replace the existing value.
        self.cursor.execute("""
            INSERT OR REPLACE INTO settings (
                key,
                value
            )
            VALUES (?, ?)
        """, (
            key,
            str(value),
        ))

        # Save the setting permanently.
        self.connection.commit()

    def get_daily_goal(self):
        # Return the daily goal as an integer.
        value = self.get_setting("daily_goal")

        if value is None:
            return 360

        try:
            return int(value)
        except ValueError:
            return 360

    def set_daily_goal(self, minutes):
        # Store the daily goal permanently as an integer value.
        minutes = max(30, min(int(minutes), 1440))
        self.set_setting("daily_goal", minutes)

    def award_activity_completion_xp(self, activity_id, amount):
        # Award completion XP only once for a completed activity.
        self.cursor.execute("""
            UPDATE activities
            SET xp_awarded = 1
            WHERE id = ?
              AND completed = 1
              AND xp_awarded = 0
        """, (activity_id,))

        if self.cursor.rowcount != 1:
            self.connection.commit()
            return self.get_total_xp_setting()

        total_xp = self.get_total_xp_setting() + amount
        self.cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value)
            VALUES ('total_xp', ?)
        """, (str(total_xp),))
        self.cursor.execute("""
            INSERT INTO xp_events (
                activity_id,
                earned_date,
                amount,
                event_type
            )
            VALUES (?, ?, ?, 'activity_completion')
        """, (
            activity_id,
            date.today().isoformat(),
            amount,
        ))
        self.connection.commit()
        return total_xp

    def get_total_xp_setting(self):
        # Read the saved XP total without creating or resetting a setting.
        value = self.get_setting("total_xp")

        if value is None:
            return 0

        return int(value)

    def record_focus_session(
        self,
        activity_id,
        started_at,
        completed_at,
        actual_minutes,
        actual_seconds=None,
    ):
        # Persist the real session timing needed to identify focus periods.
        # actual_seconds keeps the precise elapsed execution time (paused
        # time is never counted) without changing the existing minute-level
        # field used by the UI and analytics.
        self.cursor.execute("""
            INSERT INTO focus_sessions (
                activity_id,
                session_date,
                started_at,
                completed_at,
                actual_minutes,
                actual_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            activity_id,
            date.today().isoformat(),
            started_at,
            completed_at,
            max(0, int(actual_minutes)),
            None if actual_seconds is None else max(0, int(actual_seconds)),
        ))
        self.connection.commit()

    def get_earliest_record_date(self):
        """Return the earliest date with any persisted activity, session or
        XP event, or ``None`` when the database is empty. Used to define the
        "All Time" insights range from real data."""
        self.cursor.execute("""
            SELECT MIN(earliest_date) FROM (
                SELECT MIN(date) AS earliest_date FROM activities
                UNION ALL
                SELECT MIN(session_date) FROM focus_sessions
                UNION ALL
                SELECT MIN(earned_date) FROM xp_events
            )
        """)
        row = self.cursor.fetchone()
        return row[0] if row is not None else None

    def get_planning_trend_records(self):
        """Return dated plan-vs-actual records for planning-accuracy trend
        analysis. Read-only; the CalibrationService keeps its own query and
        remains the owner of calibration statistics."""
        self.cursor.execute("""
            SELECT
                id,
                date,
                activity_type,
                original_estimate_minutes,
                estimated_minutes,
                completed,
                actual_minutes
            FROM activities
            ORDER BY date, id
        """)
        rows = self.cursor.fetchall()

        return [
            {
                "activity_id": row[0],
                "date": row[1],
                "activity_type": row[2] or "Uncategorised",
                "original_estimate_minutes": max(0, row[3] or 0),
                "estimated_minutes": max(0, row[4] or 0),
                "completed": bool(row[5]),
                "actual_minutes": max(0, row[6] or 0),
            }
            for row in rows
        ]

    def get_calibration_records(self):
        # Return the persisted records the CalibrationService needs, with
        # the same defensive value cleaning used by get_insights_records.
        # original_estimate_minutes is the estimate that existed when the
        # activity was planned; it is never affected by later edits once
        # work has been recorded.
        self.cursor.execute("""
            SELECT
                id,
                activity_type,
                name,
                original_estimate_minutes,
                estimated_minutes,
                completed,
                actual_minutes
            FROM activities
            ORDER BY date, id
        """)
        rows = self.cursor.fetchall()

        return [
            {
                "activity_id": row[0],
                "activity_type": row[1] or "Uncategorised",
                "name": row[2] or "",
                "original_estimate_minutes": max(0, row[3] or 0),
                "estimated_minutes": max(0, row[4] or 0),
                "completed": bool(row[5]),
                "actual_minutes": max(0, row[6] or 0),
            }
            for row in rows
        ]

    def get_insights_records(self, start_date, end_date):
        # Collect all persisted records required by the Insights service in a
        # small, fixed number of indexed queries. UI widgets never query data.
        self.cursor.execute("""
            SELECT date, activity_type, completed, actual_minutes
            FROM activities
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (start_date, end_date))
        activity_rows = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT session_date, started_at, actual_minutes
            FROM focus_sessions
            WHERE session_date >= ? AND session_date <= ?
            ORDER BY session_date
        """, (start_date, end_date))
        session_rows = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT earned_date, amount
            FROM xp_events
            WHERE earned_date >= ? AND earned_date <= ?
            ORDER BY earned_date
        """, (start_date, end_date))
        xp_rows = self.cursor.fetchall()

        return {
            "activities": [
                {
                    "date": row[0],
                    "activity_type": row[1],
                    "completed": bool(row[2]),
                    "actual_minutes": max(0, row[3] or 0),
                }
                for row in activity_rows
            ],
            "focus_sessions": [
                {
                    "session_date": row[0],
                    "started_at": row[1],
                    "actual_minutes": max(0, row[2] or 0),
                }
                for row in session_rows
            ],
            "xp_events": [
                {
                    "earned_date": row[0],
                    "amount": row[1] or 0,
                }
                for row in xp_rows
            ],
            "daily_goal_minutes": self.get_daily_goal(),
        }

    def update_daily_history(self, activity_date):
        # Calculate daily totals from the activities table.
        self.cursor.execute("""
            SELECT
                COUNT(*),
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN completed = 1 THEN actual_minutes ELSE 0 END)
            FROM activities
            WHERE date = ?
        """, (activity_date,))

        row = self.cursor.fetchone()

        total_activities = row[0] or 0
        completed_activities = row[1] or 0
        study_minutes = row[2] or 0

        daily_goal = self.get_daily_goal()
        goal_completed = 0

        if study_minutes >= daily_goal:
            goal_completed = 1

        # Insert a new history row or update the existing row for this date.
        self.cursor.execute("""
            INSERT INTO daily_history (
                date,
                study_minutes,
                completed_activities,
                total_activities,
                goal_completed
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                study_minutes = excluded.study_minutes,
                completed_activities = excluded.completed_activities,
                total_activities = excluded.total_activities,
                goal_completed = excluded.goal_completed
        """, (
            activity_date,
            study_minutes,
            completed_activities,
            total_activities,
            goal_completed,
        ))

        # Save the history update permanently.
        self.connection.commit()

    def get_daily_history(self):
        # Return all daily history rows, newest date first.
        self.cursor.execute("""
            SELECT
                id,
                date,
                study_minutes,
                completed_activities,
                total_activities,
                goal_completed
            FROM daily_history
            ORDER BY date DESC
        """)

        return self.cursor.fetchall()

    def get_history_for_date(self, activity_date):
        # Return one daily history row for a specific date.
        self.cursor.execute("""
            SELECT
                id,
                date,
                study_minutes,
                completed_activities,
                total_activities,
                goal_completed
            FROM daily_history
            WHERE date = ?
        """, (activity_date,))

        return self.cursor.fetchone()

    def get_day_details(self, activity_date):
        """Fetch all details for a single day required by History's Day Snapshot.

        Returns a dictionary containing daily_history summary, activities list,
        focus_sessions list, xp_events list, total_xp, and daily_goal.
        """
        history_row = self.get_history_for_date(activity_date)

        self.cursor.execute("""
            SELECT
                id,
                date,
                activity_type,
                name,
                estimated_minutes,
                original_estimate_minutes,
                completed,
                actual_minutes,
                xp_awarded
            FROM activities
            WHERE date = ?
            ORDER BY id ASC
        """, (activity_date,))
        activity_rows = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT
                id,
                activity_id,
                session_date,
                started_at,
                completed_at,
                actual_minutes,
                actual_seconds
            FROM focus_sessions
            WHERE session_date = ?
            ORDER BY started_at ASC
        """, (activity_date,))
        session_rows = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT
                id,
                activity_id,
                earned_date,
                amount,
                event_type
            FROM xp_events
            WHERE earned_date = ?
            ORDER BY id ASC
        """, (activity_date,))
        xp_rows = self.cursor.fetchall()

        total_xp = sum(row[3] or 0 for row in xp_rows)
        daily_goal = self.get_daily_goal()

        return {
            "date": activity_date,
            "history": history_row,
            "activities": [
                {
                    "id": row[0],
                    "date": row[1],
                    "activity_type": row[2],
                    "name": row[3],
                    "estimated_minutes": row[4],
                    "original_estimate_minutes": row[5],
                    "completed": bool(row[6]),
                    "actual_minutes": max(0, row[7] or 0),
                    "xp_awarded": row[8] or 0,
                }
                for row in activity_rows
            ],
            "focus_sessions": [
                {
                    "id": row[0],
                    "activity_id": row[1],
                    "session_date": row[2],
                    "started_at": row[3],
                    "completed_at": row[4],
                    "actual_minutes": max(0, row[5] or 0),
                    "actual_seconds": row[6],
                }
                for row in session_rows
            ],
            "xp_events": [
                {
                    "id": row[0],
                    "activity_id": row[1],
                    "earned_date": row[2],
                    "amount": row[3] or 0,
                    "event_type": row[4],
                }
                for row in xp_rows
            ],
            "total_xp": total_xp,
            "daily_goal": daily_goal,
        }


    def close(self):
        # Close the database connection when the app exits.
        self.connection.close()
