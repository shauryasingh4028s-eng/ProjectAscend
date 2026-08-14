from datetime import date, timedelta


class StreakManager:
    def __init__(self, database):
        # Store the database so streak data can be loaded from daily history.
        self.database = database

    def get_current_streak(self):
        # Return the active streak ending today, or yesterday if today is not done.
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

    def get_longest_streak(self):
        # Return the longest consecutive goal-completed streak in history.
        history = self.get_history_by_date()

        if not history:
            return 0

        completed_dates = sorted(history.keys())
        longest_streak = 0
        current_streak = 0
        previous_date = None

        for activity_date in completed_dates:
            if not history[activity_date]:
                current_streak = 0
                previous_date = activity_date
                continue

            if previous_date is None:
                current_streak = 1
            elif activity_date == previous_date + timedelta(days=1):
                current_streak += 1
            else:
                current_streak = 1

            if current_streak > longest_streak:
                longest_streak = current_streak

            previous_date = activity_date

        return longest_streak

    def get_total_goal_days(self):
        # Return how many history days reached the daily goal.
        history_rows = self.database.get_daily_history()
        total_goal_days = 0

        for row in history_rows:
            if self.get_goal_completed_from_row(row):
                total_goal_days += 1

        return total_goal_days

    def get_completion_rate(self):
        # Return the percentage of history days where the goal was achieved.
        history_rows = self.database.get_daily_history()

        if not history_rows:
            return 0

        total_goal_days = self.get_total_goal_days()
        completion_rate = (total_goal_days / len(history_rows)) * 100

        return round(completion_rate, 1)

    def get_history_by_date(self):
        # Convert database rows into a date-to-goal-completed dictionary.
        history_rows = self.database.get_daily_history()
        history = {}

        for row in history_rows:
            activity_date = self.get_date_from_row(row)

            if activity_date is None:
                continue

            history[activity_date] = self.get_goal_completed_from_row(row)

        return history

    def get_date_from_row(self, row):
        # Extract and convert the date value from a daily history row.
        try:
            date_text = row[1]
            return date.fromisoformat(date_text)
        except (IndexError, TypeError, ValueError):
            return None

    def get_goal_completed_from_row(self, row):
        # Extract goal_completed from a daily history row.
        try:
            return bool(row[5])
        except (IndexError, TypeError):
            return False

    def is_goal_completed(self, history, activity_date):
        # Check whether the goal was completed on a specific date.
        return history.get(activity_date, False)