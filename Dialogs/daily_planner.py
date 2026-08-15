from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Dialogs.add_activity_dialog import AddActivityDialog
from Modules.capacity_service import (
    CapacityService,
    build_headline,
    build_support_lines,
)
from Modules.date_utils import format_display_date
from Modules.insights_service import format_minutes
from UI.theme.design_system import (
    ButtonFactory,
    Colors,
    IconFactory,
    Spacing,
)


class DailyPlanner(QWidget):
    def __init__(self, database, app_controller=None, capacity_service=None):
        super().__init__()

        # Store the database so this screen can load saved activities.
        self.database = database
        self.app_controller = app_controller
        # Planner Capacity Intelligence reads planned work and the user's
        # own stated available time. It never changes an activity.
        self.capacity_service = (
            capacity_service or CapacityService(database)
        )
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
        layout.addWidget(self.create_capacity_card())
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

    def create_capacity_card(self):
        """The capacity intelligence card.

        Reuses the frozen v1.3/v1.4 vocabulary only: the LearnedInsight
        surface (the established "Ascend intelligence" card, as used by
        Smart Activity Estimates), the accent glyph, CompactStatValue
        for the headline, MutedText support copy, GhostButton actions
        and the existing QSpinBox styling. No new stylesheet rules and
        no new visual language.

        The card is advisory: it reports numbers and offers control over
        the user's own available-time value. It never moves, edits,
        reorders or removes planned work.
        """
        card = QFrame()
        card.setObjectName("LearnedInsight")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD
        )
        layout.setSpacing(Spacing.XS)

        header = QHBoxLayout()
        header.setSpacing(Spacing.SM)

        glyph = QLabel("✦")
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setFixedSize(18, 18)
        # The same inline accent treatment the Smart Estimate card uses.
        glyph.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13px; font-weight: 800;"
        )

        self.capacity_headline = QLabel()
        self.capacity_headline.setObjectName("CompactStatValue")
        self.capacity_headline.setWordWrap(True)

        header.addWidget(glyph)
        header.addWidget(self.capacity_headline, 1)
        layout.addLayout(header)

        # A fixed set of support lines, hidden individually when a state
        # has nothing to say. Keeps the card from ever dominating the
        # planner while avoiding rebuilt widgets on every refresh.
        self.capacity_support_labels = []
        for _ in range(4):
            label = QLabel()
            label.setObjectName("MutedText")
            label.setWordWrap(True)
            label.setVisible(False)
            layout.addWidget(label)
            self.capacity_support_labels.append(label)

        layout.addSpacing(Spacing.XS)

        controls = QHBoxLayout()
        controls.setSpacing(Spacing.SM)

        self.available_time_caption = QLabel("Available time")
        self.available_time_caption.setObjectName("InsightMetricTitle")

        self.available_time_input = QSpinBox()
        # 0 is a real answer ("no time that day"); the upper bound
        # matches the existing full-day maximum used for the daily goal.
        self.available_time_input.setRange(0, 1440)
        self.available_time_input.setSingleStep(15)
        self.available_time_input.setSuffix(" min")
        self.available_time_input.setFixedWidth(130)

        self.set_available_time_button = self.button_factory.secondary(
            "Set", "fa5s.check"
        )
        self.set_available_time_button.clicked.connect(
            self.apply_available_time
        )
        self.clear_available_time_button = self.button_factory.secondary(
            "Clear", "fa5s.times"
        )
        self.clear_available_time_button.clicked.connect(
            self.clear_available_time
        )

        controls.addWidget(self.available_time_caption)
        controls.addWidget(self.available_time_input)
        controls.addStretch()
        for button in (
            self.set_available_time_button,
            self.clear_available_time_button,
        ):
            button.setCursor(Qt.PointingHandCursor)
            controls.addWidget(button)

        layout.addLayout(controls)

        self.capacity_card = card
        self.capacity_plan = None
        return card

    def refresh_capacity(self):
        """Recalculate and display the capacity picture.

        Capacity is recomputed on every read and never cached, so it
        adapts by construction: when available time or the plan changes,
        the next refresh simply reflects the new reality. Nothing about
        the plan is rebuilt or rewritten.
        """
        plan = self.capacity_service.build_plan(self.selected_date)
        self.capacity_plan = plan

        self.capacity_headline.setText(build_headline(plan))

        support_lines = build_support_lines(plan)
        for index, label in enumerate(self.capacity_support_labels):
            if index < len(support_lines):
                label.setText(support_lines[index])
                label.setVisible(True)
            else:
                label.clear()
                label.setVisible(False)

        # The input mirrors the stored value. With nothing stored it
        # rests at 0 and is never presented as a suggested amount: the
        # user's available time is only ever what they typed.
        self.available_time_input.blockSignals(True)
        self.available_time_input.setValue(plan.available_minutes or 0)
        self.available_time_input.blockSignals(False)

        has_available_time = plan.available_minutes is not None
        self.set_available_time_button.setText(
            "Change" if has_available_time else "Set"
        )
        self.clear_available_time_button.setVisible(has_available_time)

    def apply_available_time(self):
        """Store the available time the user explicitly entered."""
        self.capacity_service.set_available_minutes(
            self.selected_date,
            self.available_time_input.value(),
        )
        self.refresh_capacity()

    def clear_available_time(self):
        """Forget the stated available time for this date."""
        self.capacity_service.clear_available_minutes(self.selected_date)
        self.refresh_capacity()

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

        # Keep the capacity card in step with the plan it describes.
        self.refresh_capacity()

    def open_add_activity(self):
        # Open the Add Activity dialog for tomorrow's date.
        dialog = AddActivityDialog(self.database, self.selected_date)

        # If the user clicks Save, reload tomorrow's list immediately.
        if dialog.exec():
            self.load_activities()
            if self.app_controller is not None:
                self.app_controller.notify_activity_data_changed()
