from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Dialogs.add_activity_dialog import AddActivityDialog
from Modules.date_utils import format_display_date
from Modules.insights_service import format_minutes
from UI.theme.design_system import ButtonFactory, IconFactory, Spacing


class DailyPlanner(QWidget):
    def __init__(self, database, app_controller=None):
        super().__init__()

        # Store the database so this screen can load saved activities.
        self.database = database
        self.app_controller = app_controller
        # Use tomorrow as the selected date for planning.
        tomorrow = date.today() + timedelta(days=1)
        self.selected_date = tomorrow.isoformat()

        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        # Configure the planner screen.
        self.setWindowTitle("Tomorrow Planner")

        self.build_ui()

        # Show previously saved activities for tomorrow.
        self.load_activities()

    def header_actions(self):
        """Return the buttons the application shell shows in the page header."""
        return (self.add_activity_button,)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.LG)

        self.add_activity_button = self.button_factory.primary(
            "Add Activity",
            "fa5s.plus",
        )
        self.add_activity_button.clicked.connect(self.open_add_activity)

        layout.addWidget(self.create_date_card())
        layout.addWidget(self.create_activity_panel(), 1)

    def create_date_card(self):
        """Show which day is being planned, using the shared date format."""
        card = QFrame()
        card.setObjectName("HeroCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(Spacing.XL, Spacing.MD + 2, Spacing.XL, Spacing.MD + 2)
        layout.setSpacing(Spacing.LG)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        heading = QLabel("Plan Tomorrow")
        heading.setObjectName("Greeting")
        self.date_label = QLabel(
            format_display_date(self.selected_date, include_weekday=True)
        )
        self.date_label.setObjectName("MutedText")
        text_layout.addWidget(heading)
        text_layout.addWidget(self.date_label)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("CompactStatValue")
        self.summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(self.summary_label)
        return card

    def create_activity_panel(self):
        panel = QFrame()
        panel.setObjectName("ActivitySection")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        header_layout = QHBoxLayout()
        title = QLabel("Planned Activities")
        title.setObjectName("SectionTitle")
        self.count_label = QLabel()
        self.count_label.setObjectName("MutedText")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.count_label)

        self.activity_list = QListWidget()
        self.activity_list.setAlternatingRowColors(False)

        self.empty_label = QLabel(
            "Nothing planned yet. Add an activity to prepare tomorrow."
        )
        self.empty_label.setObjectName("MutedText")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)

        layout.addLayout(header_layout)
        layout.addWidget(self.activity_list, 1)
        layout.addWidget(self.empty_label, 1)
        return panel

    def load_activities(self):
        # Clear the visible list before loading fresh data from SQLite.
        self.activity_list.clear()

        # Read only activities for tomorrow's date.
        activities = self.database.get_activities_for_date(self.selected_date)

        for activity in activities:
            self.activity_list.addItem(activity.display_text())

        planned_minutes = sum(
            max(0, activity.estimated_minutes or 0) for activity in activities
        )
        has_activities = bool(activities)

        self.activity_list.setVisible(has_activities)
        self.empty_label.setVisible(not has_activities)
        activity_count = len(activities)
        activity_noun = "activity" if activity_count == 1 else "activities"
        self.count_label.setText(f"{activity_count} {activity_noun} planned")
        self.summary_label.setText(
            f"{format_minutes(planned_minutes)} planned"
            if has_activities
            else "Nothing planned"
        )

    def open_add_activity(self):
        # Open the Add Activity dialog for tomorrow's date.
        dialog = AddActivityDialog(self.database, self.selected_date)

        # If the user clicks Save, reload tomorrow's list immediately.
        if dialog.exec():
            self.load_activities()
            if self.app_controller is not None:
                self.app_controller.notify_activity_data_changed()
