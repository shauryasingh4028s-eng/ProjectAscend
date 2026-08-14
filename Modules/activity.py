from dataclasses import dataclass


@dataclass
class Activity:
    id: int | None
    date: str
    activity_type: str
    name: str
    estimated_minutes: int
    completed: bool = False
    actual_minutes: int = 0
    # The estimate that existed when the activity was planned. Frozen once
    # work is recorded so estimate calibration compares the ORIGINAL plan
    # against the actual result, not the latest edited value.
    original_estimate_minutes: int = 0

    def display_text(self):
        # Show a checkbox depending on completion status
        status = "✅" if self.completed else "⬜"

        actual = ""
        if self.completed and self.actual_minutes > 0:
            actual = f" | Actual: {self.actual_minutes} min"

        return (
            f"{status} "
            f"{self.activity_type} | "
            f"{self.name} | "
            f"{self.estimated_minutes} min"
            f"{actual}"
        )


class ActivityManager:
    def __init__(self, database=None):
        self.database = database
        self.activities = []

    def add_activity(self, activity_date, activity_type, name, estimated_minutes):
        activity = Activity(
            id=None,
            date=activity_date,
            activity_type=activity_type,
            name=name,
            estimated_minutes=estimated_minutes,
        )

        if self.database is not None:
            self.database.add_activity(activity)

        self.activities.append(activity)
        return activity

    def get_activities(self):
        if self.database is not None:
            self.activities = self.database.get_activities()

        return self.activities

    def get_activities_for_date(self, activity_date):
        if self.database is not None:
            self.activities = self.database.get_activities_for_date(activity_date)
            return self.activities

        return [
            activity
            for activity in self.activities
            if activity.date == activity_date
        ]

    def complete_activity(self, index):
        if 0 <= index < len(self.activities):
            self.activities[index].completed = True