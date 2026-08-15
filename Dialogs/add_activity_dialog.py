from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from Modules.activity import Activity
from Modules.date_utils import format_display_date
from Modules.estimate_suggestion import suggest_estimate
from UI.theme.design_system import (
    ButtonFactory,
    Colors,
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

        layout.addWidget(self.create_suggestion_area())

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

        # Smart Activity Estimates: the historical records are read once
        # when the dialog opens; recomputing a suggestion afterwards is
        # pure arithmetic on that snapshot. Nothing here ever writes to
        # the database.
        self.calibration_records = self.load_calibration_records()

        # Guard flag: True while the dialog itself is writing the spinbox
        # (accepting a suggestion). Programmatic changes must not be
        # treated as a new user anchor, otherwise accepting 70 would
        # immediately produce "suggests ~80" recommendation chaining.
        self._applying_suggestion = False

        # The suggestion re-anchors whenever the USER edits the estimate,
        # switches category, or renames the activity (the name selects
        # the exact-activity evidence tier).
        self.estimated_time.valueChanged.connect(self.refresh_suggestion)
        self.activity_type.currentTextChanged.connect(
            self.refresh_suggestion
        )
        self.activity_name.textChanged.connect(self.refresh_suggestion)

        # Initial state: anchored to the prefilled estimate in edit mode,
        # or the default value in add mode.
        self.refresh_suggestion()

    def load_calibration_records(self):
        """Read the historical plan-vs-actual records, or None when the
        data source cannot provide them. Opening the dialog must never
        fail just because suggestion evidence is unavailable."""
        try:
            return self.database.get_calibration_records()
        except Exception:
            return None

    def create_suggestion_area(self):
        """The optional suggestion card, hidden until real evidence exists.

        Visuals reuse the frozen v1.3 vocabulary only: the LearnedInsight
        card style (the established 'Ascend intelligence' surface), the
        accent glyph pattern from the Insights screen, MutedText support
        copy and GhostButton actions. No new stylesheet rules.
        """
        self.suggestion_frame = QFrame()
        self.suggestion_frame.setObjectName("LearnedInsight")

        layout = QVBoxLayout(self.suggestion_frame)
        layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD
        )
        layout.setSpacing(Spacing.XS)

        header = QHBoxLayout()
        header.setSpacing(Spacing.SM)

        glyph = QLabel("✦")
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setFixedSize(18, 18)
        # Same inline accent treatment as the LearnedInsightCard glyph.
        glyph.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13px; font-weight: 800;"
        )

        self.suggestion_headline = QLabel()
        self.suggestion_headline.setObjectName("CompactStatValue")

        header.addWidget(glyph)
        header.addWidget(self.suggestion_headline, 1)
        layout.addLayout(header)

        self.suggestion_difference = QLabel()
        self.suggestion_difference.setObjectName("MutedText")
        layout.addWidget(self.suggestion_difference)

        self.suggestion_evidence = QLabel()
        self.suggestion_evidence.setObjectName("MutedText")
        layout.addWidget(self.suggestion_evidence)

        layout.addSpacing(Spacing.XS)

        button_row = QHBoxLayout()
        button_row.setSpacing(Spacing.SM)

        self.keep_button = self.button_factory.secondary(
            "Keep", "fa5s.undo"
        )
        self.keep_button.clicked.connect(self.keep_estimate)
        self.use_button = self.button_factory.secondary(
            "Use", "fa5s.magic"
        )
        self.use_button.clicked.connect(self.use_suggestion)

        button_row.addStretch()
        for button in (self.keep_button, self.use_button):
            button.setCursor(Qt.PointingHandCursor)
            button_row.addWidget(button)
        layout.addLayout(button_row)

        # Hidden by default: with no reliable evidence the dialog stays
        # exactly as clean as it was before this feature existed.
        self.suggestion_frame.setVisible(False)
        self.current_suggestion = None

        return self.suggestion_frame

    def refresh_suggestion(self):
        """Recompute the suggestion anchored to the user's current input.

        Skipped while the dialog itself is applying an accepted suggestion
        so the accepted value never becomes a new anchor (no chaining).
        """
        if self._applying_suggestion:
            return

        suggestion = suggest_estimate(
            self.calibration_records,
            self.activity_type.currentText(),
            self.activity_name.text(),
            self.estimated_time.value(),
            self.estimated_time.minimum(),
            self.estimated_time.maximum(),
        )

        self.current_suggestion = suggestion

        if suggestion is None:
            self.suggestion_frame.setVisible(False)
            return

        self.suggestion_headline.setText(suggestion.headline)
        self.suggestion_difference.setText(suggestion.difference_text)
        self.suggestion_evidence.setText(suggestion.evidence_text)
        self.keep_button.setText(suggestion.keep_label)
        self.use_button.setText(suggestion.use_label)
        self.suggestion_frame.setVisible(True)

    def keep_estimate(self):
        """The user explicitly keeps their own estimate: the spinbox is
        untouched and the suggestion steps aside. (Ignoring the suggestion
        and pressing Save has exactly the same effect.)"""
        self.current_suggestion = None
        self.suggestion_frame.setVisible(False)

    def use_suggestion(self):
        """Apply the suggested duration to the estimate field.

        Only the input field changes; nothing is saved until the user
        presses Save. The programmatic value change is guarded so the
        accepted value is not treated as a fresh user estimate - no
        recommendation chaining. A later MANUAL edit re-anchors normally.
        """
        if self.current_suggestion is None:
            return

        self._applying_suggestion = True
        try:
            self.estimated_time.setValue(
                self.current_suggestion.suggested_minutes
            )
        finally:
            self._applying_suggestion = False

        self.current_suggestion = None
        self.suggestion_frame.setVisible(False)

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
