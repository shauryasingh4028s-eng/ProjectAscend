from pathlib import Path
from Modules.activity import Activity
from datetime import date
import sqlite3
import os


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
                actual_minutes INTEGER NOT NULL DEFAULT 0
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

        # Save table and default-setting changes to the SQLite database file.
        self.connection.commit()

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
                completed,
                actual_minutes
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            activity.date,
            activity.activity_type,
            activity.name,
            activity.estimated_minutes,
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
                completed=bool(row[5]),
                actual_minutes=row[6],
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
    ):
        # Persist the real session timing needed to identify focus periods.
        self.cursor.execute("""
            INSERT INTO focus_sessions (
                activity_id,
                session_date,
                started_at,
                completed_at,
                actual_minutes
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            activity_id,
            date.today().isoformat(),
            started_at,
            completed_at,
            max(0, int(actual_minutes)),
        ))
        self.connection.commit()

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

    def close(self):
        # Close the database connection when the app exits.
        self.connection.close()
