from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from Modules.activity import Activity
from Modules.date_utils import format_display_date
from UI.theme.design_system import (
    ButtonFactory,
    IconFactory,
    Spacing,
    ThemeManager,
)


class AddActivityDialog(QDialog):
    def __init__(self, database, selected_date, activity=None):
        super().__init__()

        self.database = database
        self.selected_date = selected_date
        self.activity = activity

        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        is_editing = activity is not None
        self.setWindowTitle("Edit Activity" if is_editing else "Add Activity")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setStyleSheet(ThemeManager.app_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        layout.setSpacing(Spacing.SM)

        heading = QLabel("Edit Activity" if is_editing else "New Activity")
        heading.setObjectName("Greeting")
        date_label = QLabel(format_display_date(self.selected_date))
        date_label.setObjectName("MutedText")
        layout.addWidget(heading)
        layout.addWidget(date_label)
        layout.addSpacing(Spacing.SM)

        layout.addWidget(self.create_field_label("Activity Type"))
        self.activity_type = QComboBox()
        self.activity_type.addItems([
            # Academic / learning
            "Tests",
            "Coding",
            "Homework",
            "Question Practice",
            "Lectures",
            "Revision",
            "Reading",
            "Assignments",
            "Project Work",
            "Research",
            "Practice",
            "Writing",
            "Note Making",
            "Skill Learning",
            "Language Learning",
            # Fitness / personal development
            "Exercise",
            "Sports",
            "Walking",
            "Meditation",
            "Planning",
            "Journaling",
            "Creative Work",
            "Music Practice",
            "Other",
        ])
        layout.addWidget(self.activity_type)

        layout.addWidget(self.create_field_label("Activity Name"))
        self.activity_name = QLineEdit()
        self.activity_name.setPlaceholderText("What will you work on?")
        layout.addWidget(self.activity_name)

        layout.addWidget(self.create_field_label("Estimated Time"))
        self.estimated_time = QSpinBox()
        self.estimated_time.setRange(5, 600)
        self.estimated_time.setValue(30)
        self.estimated_time.setSingleStep(5)
        self.estimated_time.setSuffix(" min")
        layout.addWidget(self.estimated_time)

        layout.addSpacing(Spacing.SM)

        self.save_button = self.button_factory.primary("Save", "fa5s.check")
        self.save_button.clicked.connect(self.save_activity)
        self.cancel_button = self.button_factory.secondary("Cancel", "fa5s.times")
        self.cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.setSpacing(Spacing.SM)
        button_row.addStretch()
        for button in (self.cancel_button, self.save_button):
            button.setCursor(Qt.PointingHandCursor)
            button_row.addWidget(button)
        layout.addLayout(button_row)

        # Fill existing values when editing.
        if self.activity is not None:
            self.activity_type.setCurrentText(
                self.activity.activity_type
            )
            self.activity_name.setText(
                self.activity.name
            )
            self.estimated_time.setValue(
                self.activity.estimated_minutes
            )

    @staticmethod
    def create_field_label(text):
        label = QLabel(text)
        label.setObjectName("InsightMetricTitle")
        return label

    def save_activity(self):
        if self.activity is None:
            activity = Activity(
                id=None,
                date=self.selected_date,
                activity_type=self.activity_type.currentText(),
                name=self.activity_name.text().strip(),
                estimated_minutes=self.estimated_time.value(),
            )

            self.database.add_activity(activity)

        else:
            self.activity.activity_type = (
                self.activity_type.currentText()
            )
            self.activity.name = (
                self.activity_name.text().strip()
            )
            self.activity.estimated_minutes = (
                self.estimated_time.value()
            )

            self.database.update_activity(self.activity)

        self.accept()
