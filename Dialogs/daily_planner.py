from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Dialogs.add_activity_dialog import AddActivityDialog
from Modules.capacity_service import (
    CapacityService,
    ESTIMATE_MAX_MINUTES,
    ESTIMATE_MIN_MINUTES,
    build_headline,
    build_support_lines,
    format_capacity_duration,
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
        # What-if values belong only to this live planner widget. They are
        # keyed by persisted activity ID and are never written to SQLite.
        self.temporary_allocations = {}
        self._distribution_source_signature = None
        self._distribution_seeds = {}
        self.allocation_rows = {}
        self.preview_plan = None
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
        layout.addWidget(self.create_time_distribution_section())
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

    def create_time_distribution_section(self):
        """Build the compact, temporary allocation what-if surface."""
        section = QFrame()
        section.setObjectName("ActivitySection")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        title = QLabel("Time Distribution")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.distribution_scroll = QScrollArea()
        self.distribution_scroll.setWidgetResizable(True)
        self.distribution_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.distribution_scroll.setMaximumHeight(196)
        self.distribution_rows_widget = QWidget()
        self.distribution_rows_layout = QVBoxLayout(self.distribution_rows_widget)
        self.distribution_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.distribution_rows_layout.setSpacing(Spacing.XS)
        self.distribution_scroll.setWidget(self.distribution_rows_widget)
        layout.addWidget(self.distribution_scroll)

        self.distribution_balance_label = QLabel()
        self.distribution_balance_label.setObjectName("MutedText")
        self.distribution_result_label = QLabel()
        self.distribution_result_label.setObjectName("CompactStatValue")
        self.distribution_result_label.setWordWrap(True)
        layout.addWidget(self.distribution_balance_label)
        layout.addWidget(self.distribution_result_label)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.reset_allocations_button = self.button_factory.secondary(
            "Reset", "fa5s.undo"
        )
        self.reset_allocations_button.setCursor(Qt.PointingHandCursor)
        self.reset_allocations_button.clicked.connect(
            self.reset_temporary_allocations
        )
        action_row.addWidget(self.reset_allocations_button)
        layout.addLayout(action_row)

        self.time_distribution_section = section
        section.setVisible(False)
        return section

    def clear_distribution_rows(self):
        while self.distribution_rows_layout.count():
            item = self.distribution_rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.allocation_rows = {}

    def refresh_time_distribution(self):
        """Render the in-memory allocation scenario and its capacity result."""
        base_plan = self.capacity_plan
        tasks = tuple(base_plan.tasks) if base_plan is not None else ()
        signature = tuple((task.activity_id, task.expected_minutes) for task in tasks)

        # A saved-plan change starts a fresh scenario; stale IDs have no
        # meaning in a temporary allocation experiment.
        if signature != self._distribution_source_signature:
            self.temporary_allocations.clear()
            self._distribution_source_signature = signature
        self._distribution_seeds = {
            task.activity_id: task.expected_minutes
            for task in tasks if task.activity_id is not None
        }
        self.temporary_allocations = {
            activity_id: minutes
            for activity_id, minutes in self.temporary_allocations.items()
            if activity_id in self._distribution_seeds
        }

        has_tasks = bool(tasks)
        self.time_distribution_section.setVisible(has_tasks)
        if not has_tasks:
            self.preview_plan = None
            return

        self.preview_plan = self.capacity_service.build_plan(
            self.selected_date,
            allocation_overrides=self.temporary_allocations,
        )
        # One to four rows stay compact; larger plans scroll rather than
        # pushing the saved activity list out of the planner.
        self.distribution_scroll.setFixedHeight(
            min(196, max(42, len(tasks) * 42 + 4))
        )
        self.clear_distribution_rows()
        preview_by_id = {
            task.activity_id: task for task in self.preview_plan.tasks
        }
        for task in tasks:
            preview_task = preview_by_id.get(task.activity_id, task)
            row = QFrame()
            row.setObjectName("CompactStatRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(
                Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS
            )
            row_layout.setSpacing(Spacing.SM)
            name = QLabel(task.name or task.activity_type or "Activity")
            name.setObjectName("InsightMetricTitle")
            name.setWordWrap(True)
            name.setMinimumWidth(0)
            minus = self.button_factory.icon_button("fa5s.minus")
            plus = self.button_factory.icon_button("fa5s.plus")
            for button in (minus, plus):
                button.setCursor(Qt.PointingHandCursor)
            allocation = QLabel(f"{preview_task.expected_minutes} min")
            allocation.setObjectName("CompactStatValue")
            allocation.setAlignment(Qt.AlignCenter)
            allocation.setMinimumWidth(72)
            minus.setEnabled(preview_task.expected_minutes > ESTIMATE_MIN_MINUTES)
            plus.setEnabled(preview_task.expected_minutes < ESTIMATE_MAX_MINUTES)
            activity_id = task.activity_id
            minus.clicked.connect(
                lambda checked=False, key=activity_id:
                self.change_temporary_allocation(key, -5)
            )
            plus.clicked.connect(
                lambda checked=False, key=activity_id:
                self.change_temporary_allocation(key, 5)
            )
            row_layout.addWidget(name, 1)
            row_layout.addWidget(minus)
            row_layout.addWidget(allocation)
            row_layout.addWidget(plus)
            self.distribution_rows_layout.addWidget(row)
            self.allocation_rows[activity_id] = (minus, allocation, plus)

        available = self.preview_plan.available_minutes
        allocated = self.preview_plan.expected_workload_minutes
        if available is None:
            self.distribution_balance_label.setText(
                f"Allocated {format_capacity_duration(allocated)}"
            )
            self.distribution_result_label.setText(
                "Set available time to see if it fits."
            )
        else:
            self.distribution_balance_label.setText(
                f"Available {format_capacity_duration(available)} · "
                f"Allocated {format_capacity_duration(allocated)}"
            )
            if self.preview_plan.remaining_capacity_minutes < 0:
                over_capacity = format_capacity_duration(
                    self.preview_plan.over_capacity_minutes
                )
                self.distribution_result_label.setText(
                    f"⚠ {over_capacity} over your available time"
                )
            elif self.preview_plan.remaining_capacity_minutes == 0:
                self.distribution_result_label.setText(
                    "✓ Fits — fills your available time"
                )
            else:
                remaining = format_capacity_duration(
                    self.preview_plan.open_capacity_minutes
                )
                self.distribution_result_label.setText(
                    f"✓ Fits — {remaining} remaining"
                )
        self.reset_allocations_button.setVisible(bool(self.temporary_allocations))

    def change_temporary_allocation(self, activity_id, delta):
        """Change only the local what-if allocation for one pending task."""
        if activity_id not in self._distribution_seeds:
            return
        current = self.temporary_allocations.get(
            activity_id, self._distribution_seeds[activity_id]
        )
        updated = max(
            ESTIMATE_MIN_MINUTES,
            min(ESTIMATE_MAX_MINUTES, current + delta),
        )
        if updated == self._distribution_seeds[activity_id]:
            self.temporary_allocations.pop(activity_id, None)
        else:
            self.temporary_allocations[activity_id] = updated
        self.refresh_time_distribution()

    def reset_temporary_allocations(self):
        self.temporary_allocations.clear()
        self.refresh_time_distribution()

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
        self.refresh_time_distribution()

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
