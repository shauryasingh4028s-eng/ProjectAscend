from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal


class SessionEngine(QObject):
    timer_updated = Signal(int)
    session_started = Signal(object)
    session_paused = Signal()
    session_resumed = Signal()
    session_completed = Signal(object)

    def __init__(self, database):
        super().__init__()

        # Store the database so completed sessions can be saved.
        self.database = database

        # Keep track of the activity currently being worked on.
        self.current_activity = None

        # Store elapsed time in seconds because the timer ticks every second.
        self.elapsed_seconds = 0

        # Preserve the local start time for the persisted focus-session log.
        self.session_started_at = None

        # Remember whether the timer is currently running.
        self.is_running = False

        # QTimer is the correct Qt tool for live UI timers.
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_elapsed_time)

    def start(self, activity):
        # Start a new session for the selected activity.
        self.current_activity = activity
        self.elapsed_seconds = 0
        self.session_started_at = datetime.now()
        self.is_running = True
        self.timer.start()
        self.session_started.emit(activity)
        self.timer_updated.emit(self.elapsed_seconds)

    def pause(self):
        # Pause the timer without clearing the current activity.
        if self.current_activity is None:
            return

        self.timer.stop()
        self.is_running = False
        self.session_paused.emit()

    def resume(self):
        # Continue the timer after it has been paused.
        if self.current_activity is None:
            return

        self.timer.start()
        self.is_running = True
        self.session_resumed.emit()

    def complete(self):
        # Finish the current session and save the result to SQLite.
        if self.current_activity is None:
            return

        self.timer.stop()
        self.is_running = False

        actual_minutes = self.convert_seconds_to_minutes(self.elapsed_seconds)
        self.current_activity.actual_minutes = actual_minutes
        self.current_activity.completed = True

        self.database.update_activity(self.current_activity)
        self.database.record_focus_session(
            self.current_activity.id,
            self.session_started_at.isoformat(timespec="seconds"),
            datetime.now().isoformat(timespec="seconds"),
            actual_minutes,
            # Keep the exact elapsed execution seconds (pause time is never
            # counted) for future precise analytics. The minute-level
            # actual_minutes field remains the canonical UI value.
            actual_seconds=self.elapsed_seconds,
        )
        self.session_completed.emit(self.current_activity)

        self.current_activity = None
        self.elapsed_seconds = 0
        self.session_started_at = None
        self.timer_updated.emit(self.elapsed_seconds)

    def update_elapsed_time(self):
        # Add one second and tell the dashboard to refresh the timer label.
        self.elapsed_seconds += 1
        self.timer_updated.emit(self.elapsed_seconds)

    def convert_seconds_to_minutes(self, seconds):
        # Convert seconds into whole minutes for database storage.
        if seconds <= 0:
            return 0

        return (seconds + 59) // 60

    def format_time(self, seconds):
        # Convert seconds into HH:MM:SS text for the dashboard.
        hours = seconds // 3600
        remaining_seconds = seconds % 3600
        minutes = remaining_seconds // 60
        final_seconds = remaining_seconds % 60

        return f"{hours:02}:{minutes:02}:{final_seconds:02}"
