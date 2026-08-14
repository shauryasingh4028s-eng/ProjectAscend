"""The Project Ascend History page.

Presentation-only. Every value shown here comes from the existing
``Database.get_daily_history()`` rows; this module performs no database
writes, no analytics and no date arithmetic of its own.

Row layout (unchanged):
    0 id | 1 date | 2 study_minutes | 3 completed_activities
    4 total_activities | 5 goal_completed
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Modules.date_utils import format_display_date, parse_iso_date
from Modules.insights_service import format_day_count, format_minutes
from UI.theme.design_system import (
    ButtonFactory,
    Colors,
    IconFactory,
    Radius,
    Spacing,
)


class HistorySummaryCard(QFrame):
    """Compact metric tile, styled with the shared Insights card tokens."""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM + 2, Spacing.MD, Spacing.SM + 2)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("InsightMetricTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("InsightMetricValue")
        self.note_label = QLabel()
        self.note_label.setObjectName("InsightMetricNote")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_value(self, value, note=""):
        self.value_label.setText(value)
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))


class HistoryEntry(QFrame):
    """One saved productivity day, rendered as a compact record card."""

    def __init__(self, entry_date, focus_minutes, completed, total, goal_met):
        super().__init__()
        self.setObjectName("HistoryEntry")
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM + 2, Spacing.MD, Spacing.SM + 2)
        layout.setSpacing(Spacing.MD)

        layout.addWidget(self.create_timeline_marker(goal_met))
        layout.addLayout(self.create_date_block(entry_date), 0)
        layout.addStretch(1)
        layout.addLayout(
            self.create_metrics_block(focus_minutes, completed, total)
        )
        layout.addWidget(self.create_status_badge(goal_met))

    def create_timeline_marker(self, goal_met):
        """Small dot giving the list a subtle timeline reading order."""
        accent = Colors.SUCCESS if goal_met else Colors.WARNING
        marker = QLabel()
        marker.setFixedSize(8, 8)
        marker.setStyleSheet(
            f"background-color: {accent}; border-radius: 4px;"
        )
        holder = QWidget()
        holder.setFixedWidth(14)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(marker, alignment=Qt.AlignCenter)
        return holder

    def create_date_block(self, entry_date):
        layout = QVBoxLayout()
        layout.setSpacing(1)

        date_label = QLabel(format_display_date(entry_date))
        date_label.setObjectName("HistoryDate")

        parsed_date = parse_iso_date(entry_date)
        weekday_text = parsed_date.strftime("%A") if parsed_date else ""
        weekday_label = QLabel(weekday_text)
        weekday_label.setObjectName("HistoryWeekday")

        layout.addWidget(date_label)
        layout.addWidget(weekday_label)
        return layout

    def create_metrics_block(self, focus_minutes, completed, total):
        layout = QHBoxLayout()
        layout.setSpacing(Spacing.XL)
        layout.addLayout(
            self.create_metric("Focus", format_minutes(focus_minutes))
        )
        layout.addLayout(
            self.create_metric("Completed", f"{completed} / {total}")
        )
        return layout

    @staticmethod
    def create_metric(title, value):
        layout = QVBoxLayout()
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("HistoryMetricLabel")
        value_label = QLabel(value)
        value_label.setObjectName("HistoryMetricValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return layout

    @staticmethod
    def create_status_badge(goal_met):
        badge = QLabel("Goal achieved" if goal_met else "Goal missed")
        badge.setObjectName(
            "HistoryBadgeAchieved" if goal_met else "HistoryBadgeMissed"
        )
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(110)
        return badge


class HistoryEmptyState(QWidget):
    """Polished placeholder shown when no productivity days exist yet."""

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, Spacing.XXL, 0, Spacing.XXL)
        layout.setSpacing(Spacing.SM)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("◷")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(52, 52)
        icon.setStyleSheet(
            f"background-color: {Colors.SURFACE_SECONDARY};"
            f"border: 1px solid {Colors.BORDER};"
            f"border-radius: {Radius.XL}px;"
            f"color: {Colors.PRIMARY}; font-size: 22px;"
        )

        title = QLabel("No history yet")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)

        message = QLabel(
            "Complete activities and focus sessions to build your timeline.\n"
            "Each finished day is saved here automatically."
        )
        message.setObjectName("MutedText")
        message.setAlignment(Qt.AlignCenter)

        layout.addWidget(icon, alignment=Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(message)


class HistoryWindow(QWidget):
    def __init__(self, database):
        super().__init__()

        # Store the shared database connection.
        self.database = database

        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)
        self.summary_cards = {}

        # Configure the history screen.
        self.setWindowTitle("Project Ascend - History")

        # Build the interface and load saved history.
        self.build_ui()
        self.load_history()

    def header_actions(self):
        """Return the buttons the application shell shows in the page header."""
        return (self.refresh_button,)

    def build_ui(self):
        # Create the main layout for the history page.
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.refresh_button = self.button_factory.secondary("Refresh", "fa5s.sync")
        self.refresh_button.clicked.connect(self.load_history)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(Spacing.XXL, Spacing.LG, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.MD)

        subtitle = QLabel("Your productivity timeline")
        subtitle.setObjectName("MutedText")
        layout.addWidget(subtitle)

        self.summary_row = self.create_summary_row()
        layout.addWidget(self.summary_row)

        self.timeline_section = self.create_timeline_section()
        layout.addWidget(self.timeline_section)

        self.empty_state = HistoryEmptyState()
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        layout.addStretch()

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def create_summary_row(self):
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.MD)

        self.summary_cards = {
            "active": HistorySummaryCard("Active Days"),
            "average": HistorySummaryCard("Average Focus"),
            "achieved": HistorySummaryCard("Goals Achieved"),
        }
        for column, card in enumerate(self.summary_cards.values()):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        return container

    def create_timeline_section(self):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(section)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        header_layout = QHBoxLayout()
        title = QLabel("Recorded Days")
        title.setObjectName("SectionTitle")
        self.count_label = QLabel()
        self.count_label.setObjectName("MutedText")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.count_label)

        self.entries_layout = QVBoxLayout()
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(Spacing.SM)

        layout.addLayout(header_layout)
        layout.addLayout(self.entries_layout)
        return section

    def load_history(self):
        # Reload history rows from SQLite.
        history_rows = self.database.get_daily_history()

        self.clear_entries()
        for row in history_rows:
            self.entries_layout.addWidget(self.create_entry(row))

        self.update_summary(history_rows)

        has_rows = bool(history_rows)
        self.summary_row.setVisible(has_rows)
        self.timeline_section.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

    @staticmethod
    def create_entry(row):
        """Build one entry card from an unmodified daily_history row."""
        return HistoryEntry(
            entry_date=row[1],
            focus_minutes=row[2],
            completed=row[3],
            total=row[4],
            goal_met=bool(row[5]),
        )

    def update_summary(self, history_rows):
        """Summarize only what the saved history rows already contain."""
        recorded_days = len(history_rows)
        if recorded_days == 0:
            for card in self.summary_cards.values():
                card.set_value("—", "")
            self.count_label.setText("")
            return

        active_days = sum(1 for row in history_rows if (row[2] or 0) > 0)
        total_minutes = sum(max(0, row[2] or 0) for row in history_rows)
        goals_achieved = sum(1 for row in history_rows if bool(row[5]))
        average_minutes = round(total_minutes / recorded_days)
        achieved_rate = round(goals_achieved / recorded_days * 100)

        self.summary_cards["active"].set_value(
            f"{active_days}",
            f"of {format_day_count(recorded_days)} recorded",
        )
        self.summary_cards["average"].set_value(
            format_minutes(average_minutes),
            f"{format_minutes(total_minutes)} total",
        )
        self.summary_cards["achieved"].set_value(
            f"{goals_achieved}",
            f"{achieved_rate}% of recorded days",
        )
        self.count_label.setText(f"{format_day_count(recorded_days)} recorded")

    def clear_entries(self):
        # setParent(None) detaches immediately, so a refresh can never leave
        # stale cards alive while deleteLater() is still pending.
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
