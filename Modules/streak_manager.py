from datetime import date, timedelta


BEST_STREAK_SETTING = "best_streak"


class StreakManager:
    def __init__(self, database):
        # Daily history remains the authoritative streak-day source.
        self.database = database

    def get_current_streak(self):
        """Return the active streak ending today or yesterday.

        A day only enters the streak when persisted daily history says its
        daily productivity goal was reached. Productive work below the goal is
        retained in statistics but does not create a streak day.
        """
        history = self.get_history_by_date()
        today = date.today()
        yesterday = today - timedelta(days=1)

        if self.is_goal_completed(history, today):
            start_date = today
        elif self.is_goal_completed(history, yesterday):
            start_date = yesterday
        else:
            return 0

        streak = 0
        current_date = start_date
        while self.is_goal_completed(history, current_date):
            streak += 1
            current_date -= timedelta(days=1)
        return streak

    def _calculated_longest_streak(self):
        history = self.get_history_by_date()
        completed_dates = sorted(
            activity_date
            for activity_date, completed in history.items()
            if completed
        )
        if not completed_dates:
            return 0

        longest = 1
        running = 1
        previous = completed_dates[0]
        for activity_date in completed_dates[1:]:
            if activity_date == previous + timedelta(days=1):
                running += 1
            else:
                running = 1
            longest = max(longest, running)
            previous = activity_date
        return longest

    def _saved_best_streak(self):
        raw_value = self.database.get_setting(BEST_STREAK_SETTING)
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return 0

    def get_longest_streak(self):
        """Return and permanently retain the user's best streak."""
        calculated = self._calculated_longest_streak()
        saved = self._saved_best_streak()
        best = max(calculated, saved)
        if best > saved:
            self.database.set_setting(BEST_STREAK_SETTING, best)
        return best

    def get_total_goal_days(self):
        return sum(
            1
            for row in self.database.get_daily_history()
            if self.get_goal_completed_from_row(row)
        )

    def get_completion_rate(self):
        history_rows = self.database.get_daily_history()
        if not history_rows:
            return 0
        return round((self.get_total_goal_days() / len(history_rows)) * 100, 1)

    def get_history_by_date(self):
        history = {}
        for row in self.database.get_daily_history():
            activity_date = self.get_date_from_row(row)
            if activity_date is not None:
                history[activity_date] = self.get_goal_completed_from_row(row)
        return history

    def get_date_from_row(self, row):
        try:
            return date.fromisoformat(row[1])
        except (IndexError, TypeError, ValueError):
            return None

    def get_goal_completed_from_row(self, row):
        try:
            return bool(row[5])
        except (IndexError, TypeError):
            return False

    def is_goal_completed(self, history, activity_date):
        return history.get(activity_date, False)
