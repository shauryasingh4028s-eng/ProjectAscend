from PySide6.QtCore import QObject, Signal

class XPManager(QObject):
    level_changed = Signal(int, str)

    def __init__(self, database):
        super().__init__()
        # Store the shared database connection.
        self.database = database

    def get_total_xp(self):
        # Read the total XP from the settings table.
        xp = self.database.get_setting("total_xp")

        if xp is None:
            self.database.set_setting("total_xp", 0)
            return 0

        return int(xp)

    def add_xp(self, amount):
        # Increase total XP permanently.
        total_xp = self.get_total_xp()
        old_level = self.get_level()
        total_xp += amount
        self.database.set_setting("total_xp", total_xp)
        new_level = self.get_level()

        if new_level > old_level:
            self.level_changed.emit(new_level, f"Level {new_level}")

        return total_xp

    def get_level(self):
        # Calculate the user's level.
        total_xp = self.get_total_xp()
        return (total_xp // 100) + 1

    def award_activity_completion(self, activity_id=None):
        # Award XP for completing one activity.
        if activity_id is not None:
            return self.database.award_activity_completion_xp(
                activity_id,
                10,
            )

        return self.add_xp(10)

    def award_daily_goal(self):
        # Award XP for completing the daily goal.
        return self.add_xp(50)
