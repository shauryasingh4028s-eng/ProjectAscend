"""The Project Ascend History page.

Master-Inspector Dual Pane layout (Concept C):
- Left Rail: Chronological activity stream grouped by recency (This Week, Last Week, Earlier).
- Right Inspector: Day Snapshot showing date context, status banner, 4 key metrics, factual reflection, completed activities, and focus session timeline.
- In-Canvas Responsive Layout: Dual-Pane side-by-side on wide screens (>=1180px). On compact screens (<1180px), switches smoothly between Rail and Inspector in-canvas with a close button (✕), avoiding native window destruction and event-loop lockups.
"""

from datetime import date, datetime, timedelta
from PySide6.QtCore import QSize, Qt, Signal
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
    Typography,
)


def get_recency_group(iso_date_str):
    """Categorise an ISO date string into a human-friendly chronological group."""
    parsed = parse_iso_date(iso_date_str)
    if parsed is None:
        return "EARLIER HISTORY"

    today = date.today()
    # Beginning of current week (Monday)
    current_monday = today - timedelta(days=today.weekday())
    last_monday = current_monday - timedelta(days=7)

    if parsed >= current_monday:
        return "THIS WEEK"
    elif parsed >= last_monday:
        return "LAST WEEK"
    elif parsed.year == today.year and parsed.month == today.month:
        return "EARLIER THIS MONTH"
    else:
        return parsed.strftime("%B %Y").upper()


class HistoryDayCard(QFrame):
    """Compact historical day summary card in the left chronological rail."""

    clicked = Signal(str)

    def __init__(self, entry_date, focus_minutes, completed, total, goal_met, icon_factory):
        super().__init__()
        self.entry_date = entry_date
        self.icon_factory = icon_factory
        self.selected = False

        self.setObjectName("HistoryDayCard")
        self.setFixedHeight(64)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(Spacing.SM)

        # Left active indicator strip (primary blue when selected)
        self.indicator = QFrame()
        self.indicator.setFixedWidth(4)
        self.indicator.setFixedHeight(44)
        self.indicator.setStyleSheet("background-color: transparent; border-radius: 2px;")
        layout.addWidget(self.indicator)

        # Date icon
        icon_color = Colors.PRIMARY if goal_met else Colors.TEXT_MUTED
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setPixmap(
            self.icon_factory.get("fa5s.calendar-day", icon_color).pixmap(QSize(18, 18))
        )
        layout.addWidget(icon_label)

        # Date & Subtitle
        date_block = QVBoxLayout()
        date_block.setSpacing(1)

        self.date_label = QLabel(format_display_date(entry_date))
        self.date_label.setObjectName("HistoryDate")

        parsed_date = parse_iso_date(entry_date)
        relative_text = ""
        if parsed_date:
            today = date.today()
            if parsed_date == today:
                relative_text = "Today"
            elif parsed_date == today - timedelta(days=1):
                relative_text = "Yesterday"
            else:
                relative_text = parsed_date.strftime("%A")

        self.weekday_label = QLabel(relative_text)
        self.weekday_label.setObjectName("HistoryWeekday")

        date_block.addWidget(self.date_label)
        date_block.addWidget(self.weekday_label)
        layout.addLayout(date_block, 1)

        # Metrics block (Focus duration & tasks completed)
        metrics_block = QVBoxLayout()
        metrics_block.setSpacing(1)
        metrics_block.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        focus_text = format_minutes(focus_minutes) if focus_minutes > 0 else "0m focus"
        tasks_text = f"{completed}/{total} tasks" if total > 0 else "0 tasks"

        focus_lbl = QLabel(focus_text)
        focus_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        focus_lbl.setAlignment(Qt.AlignRight)

        tasks_lbl = QLabel(tasks_text)
        tasks_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        tasks_lbl.setAlignment(Qt.AlignRight)

        metrics_block.addWidget(focus_lbl)
        metrics_block.addWidget(tasks_lbl)
        layout.addLayout(metrics_block)

        # Status badge
        badge_text = "Goal met" if goal_met else ("Rest" if total == 0 and focus_minutes == 0 else "Missed")
        badge_obj = "HistoryBadgeAchieved" if goal_met else ("HistoryBadgeRest" if total == 0 and focus_minutes == 0 else "HistoryBadgeMissed")
        badge = QLabel(badge_text)
        badge.setObjectName(badge_obj)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(70)
        layout.addWidget(badge)

    def set_selected(self, selected):
        self.selected = selected
        self.setProperty("selected", "true" if selected else "false")
        if selected:
            self.indicator.setStyleSheet(f"background-color: {Colors.PRIMARY}; border-radius: 2px;")
            self.setStyleSheet(
                f"QFrame#HistoryDayCard {{ background-color: {Colors.SURFACE_ELEVATED}; border: 1px solid {Colors.PRIMARY}; border-radius: {Radius.MD}px; }}"
            )
        else:
            self.indicator.setStyleSheet("background-color: transparent; border-radius: 2px;")
            self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.entry_date)
        super().mousePressEvent(event)


class DaySnapshotWidget(QFrame):
    """Right-hand Inspector panel displaying complete details for a selected day."""

    day_navigated = Signal(str)
    close_requested = Signal()

    def __init__(self, database, icon_factory, button_factory):
        super().__init__()
        self.database = database
        self.icon_factory = icon_factory
        self.button_factory = button_factory
        self.current_date = None
        self.has_prev = False
        self.has_next = False
        self.compact_mode = False

        self.setObjectName("DaySnapshotSurface")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.MD)

        # 1. Header with date title and prev/next controls
        header_layout = QHBoxLayout()
        header_layout.setSpacing(Spacing.SM)

        self.prev_btn = self.button_factory.icon_button("fa5s.chevron-left")
        self.prev_btn.setToolTip("Previous Day")
        self.prev_btn.clicked.connect(self._on_prev_clicked)

        self.next_btn = self.button_factory.icon_button("fa5s.chevron-right")
        self.next_btn.setToolTip("Next Day")
        self.next_btn.clicked.connect(self._on_next_clicked)

        self.title_label = QLabel("Select a Day")
        self.title_label.setObjectName("DaySnapshotTitle")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.close_btn = self.button_factory.icon_button("fa5s.times")
        self.close_btn.setToolTip("Back to History Rail")
        self.close_btn.clicked.connect(self.close_requested.emit)
        self.close_btn.setVisible(False)

        header_layout.addWidget(self.prev_btn)
        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.next_btn)
        header_layout.addWidget(self.close_btn)

        main_layout.addLayout(header_layout)

        # Scrollable content body for inspector
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        self.body_layout = QVBoxLayout(content)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(Spacing.MD)

        # 2. Status Banner
        self.status_banner = QFrame()
        self.status_banner.setObjectName("DaySnapshotStatusBanner")
        banner_layout = QHBoxLayout(self.status_banner)
        banner_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        banner_layout.setSpacing(Spacing.MD)

        self.status_icon = QLabel()
        self.status_icon.setFixedSize(32, 32)

        status_text_layout = QVBoxLayout()
        status_text_layout.setSpacing(2)
        self.status_title = QLabel("—")
        self.status_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 15px; font-weight: 800;")
        self.status_subtext = QLabel("")
        self.status_subtext.setObjectName("MutedText")
        status_text_layout.addWidget(self.status_title)
        status_text_layout.addWidget(self.status_subtext)

        banner_layout.addWidget(self.status_icon)
        banner_layout.addLayout(status_text_layout, 1)
        self.body_layout.addWidget(self.status_banner)

        # 3. Metric Tiles Grid (2x2)
        metrics_container = QWidget()
        metrics_grid = QGridLayout(metrics_container)
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setSpacing(Spacing.SM)

        self.tile_focus = self._create_metric_tile("FOCUS TIME", "fa5s.clock")
        self.tile_tasks = self._create_metric_tile("COMPLETED TASKS", "fa5s.check-circle")
        self.tile_sessions = self._create_metric_tile("FOCUS SESSIONS", "fa5s.stopwatch")
        self.tile_xp = self._create_metric_tile("XP EARNED", "fa5s.star")

        metrics_grid.addWidget(self.tile_focus, 0, 0)
        metrics_grid.addWidget(self.tile_tasks, 0, 1)
        metrics_grid.addWidget(self.tile_sessions, 1, 0)
        metrics_grid.addWidget(self.tile_xp, 1, 1)
        self.body_layout.addWidget(metrics_container)

        # 4. Factual Day Reflection Box
        self.reflection_box = QFrame()
        self.reflection_box.setObjectName("DaySnapshotReflectionBox")
        refl_layout = QHBoxLayout(self.reflection_box)
        refl_layout.setContentsMargins(Spacing.MD, Spacing.SM + 2, Spacing.MD, Spacing.SM + 2)
        refl_layout.setSpacing(Spacing.SM)

        refl_icon = QLabel()
        refl_icon.setFixedSize(20, 20)
        refl_icon.setPixmap(self.icon_factory.get("fa5s.info-circle", Colors.PRIMARY).pixmap(QSize(16, 16)))
        self.reflection_label = QLabel("No activity recorded for this date.")
        self.reflection_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        self.reflection_label.setWordWrap(True)

        refl_layout.addWidget(refl_icon)
        refl_layout.addWidget(self.reflection_label, 1)
        self.body_layout.addWidget(self.reflection_box)

        # 5. Completed Activities Section
        self.activities_title = QLabel("Completed Activities")
        self.activities_title.setObjectName("SectionTitle")
        self.body_layout.addWidget(self.activities_title)

        self.activities_container = QVBoxLayout()
        self.activities_container.setSpacing(Spacing.XS + 2)
        self.body_layout.addLayout(self.activities_container)

        # 6. Focus Sessions Section
        self.sessions_title = QLabel("Focus Sessions")
        self.sessions_title.setObjectName("SectionTitle")
        self.body_layout.addWidget(self.sessions_title)

        self.sessions_container = QVBoxLayout()
        self.sessions_container.setSpacing(Spacing.XS + 2)
        self.body_layout.addLayout(self.sessions_container)

        self.body_layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def set_compact_mode(self, is_compact):
        self.compact_mode = is_compact
        self.close_btn.setVisible(is_compact)

    def _create_metric_tile(self, title, icon_name):
        tile = QFrame()
        tile.setObjectName("DaySnapshotMetricTile")
        tile.setFixedHeight(68)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(Spacing.XS)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setPixmap(self.icon_factory.get(icon_name, Colors.TEXT_MUTED).pixmap(QSize(12, 12)))

        t_lbl = QLabel(title)
        t_lbl.setObjectName("InsightMetricTitle")

        header.addWidget(icon_lbl)
        header.addWidget(t_lbl)
        header.addStretch()

        val_lbl = QLabel("—")
        val_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 18px; font-weight: 800;")
        tile.val_lbl = val_lbl

        layout.addLayout(header)
        layout.addWidget(val_lbl)
        return tile

    def set_day_details(self, details, has_prev=False, has_next=False):
        self.current_date = details["date"]
        self.has_prev = has_prev
        self.has_next = has_next
        self.prev_btn.setEnabled(has_prev)
        self.next_btn.setEnabled(has_next)

        # Update Title Date
        formatted_date = format_display_date(details["date"], include_weekday=True)
        self.title_label.setText(formatted_date)

        history_row = details.get("history")
        study_mins = history_row[2] if history_row else 0
        completed_tasks = history_row[3] if history_row else 0
        total_tasks = history_row[4] if history_row else 0
        goal_completed = bool(history_row[5]) if history_row else False
        daily_goal = details.get("daily_goal", 60)

        # 1. Update Status Banner
        if goal_completed:
            self.status_icon.setPixmap(self.icon_factory.get("fa5s.trophy", Colors.SUCCESS).pixmap(QSize(28, 28)))
            self.status_title.setText("Goal Achieved")
            self.status_subtext.setText(f"Completed {format_minutes(study_mins)} focus (target: {daily_goal}m)")
        elif study_mins > 0 or completed_tasks > 0:
            self.status_icon.setPixmap(self.icon_factory.get("fa5s.exclamation-triangle", Colors.WARNING).pixmap(QSize(28, 28)))
            self.status_title.setText("Goal Missed")
            self.status_subtext.setText(f"Completed {format_minutes(study_mins)} focus out of {daily_goal}m target")
        else:
            self.status_icon.setPixmap(self.icon_factory.get("fa5s.moon", Colors.TEXT_MUTED).pixmap(QSize(28, 28)))
            self.status_title.setText("Rest Day")
            self.status_subtext.setText("No focus sessions or activities logged on this date")

        # 2. Update Metric Tiles
        self.tile_focus.val_lbl.setText(format_minutes(study_mins))
        self.tile_tasks.val_lbl.setText(f"{completed_tasks} / {total_tasks}" if total_tasks > 0 else "0")

        sessions_list = details.get("focus_sessions", [])
        self.tile_sessions.val_lbl.setText(f"{len(sessions_list)}")

        total_xp = details.get("total_xp", 0)
        self.tile_xp.val_lbl.setText(f"+{total_xp} XP" if total_xp > 0 else "0 XP")

        # 3. Factual Reflection Sentence
        if goal_completed and completed_tasks > 0 and completed_tasks == total_tasks:
            refl_text = f"Completed 100% of planned activities ({completed_tasks}/{total_tasks}) with {format_minutes(study_mins)} focus."
        elif goal_completed:
            refl_text = f"Reached daily focus goal with {format_minutes(study_mins)} total focus time across {len(sessions_list)} sessions."
        elif completed_tasks > 0:
            refl_text = f"Completed {completed_tasks} activities with {format_minutes(study_mins)} focus."
        elif study_mins > 0:
            refl_text = f"Logged {format_minutes(study_mins)} of focus time."
        else:
            refl_text = "Rest day with no recorded focus sessions or completed tasks."
        self.reflection_label.setText(refl_text)

        # 4. Render Completed Activities
        self._clear_layout(self.activities_container)
        activities = details.get("activities", [])
        completed_activities = [a for a in activities if a["completed"]]
        self.activities_title.setText(f"Completed Activities ({len(completed_activities)})")

        if not completed_activities:
            empty_lbl = QLabel("No completed activities recorded for this date.")
            empty_lbl.setObjectName("MutedText")
            empty_lbl.setStyleSheet("font-style: italic; padding: 4px 0;")
            self.activities_container.addWidget(empty_lbl)
        else:
            for act in completed_activities:
                act_row = QFrame()
                act_row.setObjectName("HistoryActivityItem")
                row_layout = QHBoxLayout(act_row)
                row_layout.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
                row_layout.setSpacing(Spacing.SM)

                chk = QLabel()
                chk.setFixedSize(16, 16)
                chk.setPixmap(self.icon_factory.get("fa5s.check-circle", Colors.SUCCESS).pixmap(QSize(14, 14)))

                name_lbl = QLabel(act["name"] or "Untitled activity")
                name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600;")

                dur_lbl = QLabel(format_minutes(act["actual_minutes"]))
                dur_lbl.setObjectName("MutedText")

                xp_lbl = QLabel(f"+{act['xp_awarded']} XP" if act["xp_awarded"] > 0 else "")
                xp_lbl.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700; font-size: 11px;")

                row_layout.addWidget(chk)
                row_layout.addWidget(name_lbl, 1)
                row_layout.addWidget(dur_lbl)
                row_layout.addWidget(xp_lbl)
                self.activities_container.addWidget(act_row)

        # 5. Render Focus Sessions
        self._clear_layout(self.sessions_container)
        self.sessions_title.setText(f"Focus Sessions ({len(sessions_list)})")

        if not sessions_list:
            empty_lbl = QLabel("No focus sessions recorded for this date.")
            empty_lbl.setObjectName("MutedText")
            empty_lbl.setStyleSheet("font-style: italic; padding: 4px 0;")
            self.sessions_container.addWidget(empty_lbl)
        else:
            # Map activity_id to name
            act_map = {a["id"]: a["name"] for a in activities}
            for sess in sessions_list:
                sess_row = QFrame()
                sess_row.setObjectName("HistorySessionItem")
                row_layout = QHBoxLayout(sess_row)
                row_layout.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
                row_layout.setSpacing(Spacing.SM)

                ico = QLabel()
                ico.setFixedSize(16, 16)
                ico.setPixmap(self.icon_factory.get("fa5s.stopwatch", Colors.PRIMARY).pixmap(QSize(14, 14)))

                # Format start time if available
                started_str = sess.get("started_at", "")
                time_range = started_str[:5] if len(started_str) >= 5 else ""

                act_name = act_map.get(sess.get("activity_id"), "Focus Session")
                title_text = f"{time_range} • {act_name}" if time_range else act_name

                name_lbl = QLabel(title_text)
                name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px;")

                dur_lbl = QLabel(format_minutes(sess["actual_minutes"]))
                dur_lbl.setStyleSheet(f"color: {Colors.PRIMARY_HOVER}; font-weight: 700; font-size: 12px;")

                row_layout.addWidget(ico)
                row_layout.addWidget(name_lbl, 1)
                row_layout.addWidget(dur_lbl)
                self.sessions_container.addWidget(sess_row)

    def _on_prev_clicked(self):
        if self.has_prev:
            self.day_navigated.emit("prev")

    def _on_next_clicked(self):
        if self.has_next:
            self.day_navigated.emit("next")

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


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
    """The main History screen widget implementing Concept C Dual-Pane layout."""

    COMPACT_BREAKPOINT = 1180

    def __init__(self, database):
        super().__init__()
        self.database = database
        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        self.history_rows = []
        self.dates_list = []
        self.history_cards = {}
        self.selected_date = None

        self.setWindowTitle("Project Ascend - History")
        self.build_ui()
        self.load_history()

    def header_actions(self):
        return (self.refresh_button,)

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.refresh_button = self.button_factory.secondary("Refresh", "fa5s.sync")
        self.refresh_button.clicked.connect(self.load_history)

        # Main workspace container
        self.workspace = QWidget()
        self.workspace_layout = QHBoxLayout(self.workspace)
        self.workspace_layout.setContentsMargins(Spacing.XXL, Spacing.LG, Spacing.XXL, Spacing.XXL)
        self.workspace_layout.setSpacing(Spacing.LG)

        # LEFT PANE — Chronological Rail Scroll Area
        self.rail_container = QWidget()
        rail_layout = QVBoxLayout(self.rail_container)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(Spacing.MD)

        subtitle = QLabel("Review daily achievements and focus sessions")
        subtitle.setObjectName("MutedText")
        rail_layout.addWidget(subtitle)

        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setFrameShape(QFrame.NoFrame)
        self.rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        rail_content = QWidget()
        self.entries_layout = QVBoxLayout(rail_content)
        self.entries_layout.setContentsMargins(0, 0, Spacing.SM, 0)
        self.entries_layout.setSpacing(Spacing.SM)

        self.rail_scroll.setWidget(rail_content)
        rail_layout.addWidget(self.rail_scroll)

        self.empty_state = HistoryEmptyState()
        self.empty_state.setVisible(False)
        rail_layout.addWidget(self.empty_state)

        # RIGHT PANE — Day Snapshot Inspector (In-canvas)
        self.inspector_container = QWidget()
        inspector_layout = QVBoxLayout(self.inspector_container)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        inspector_layout.setSpacing(0)

        self.inspector_snapshot = DaySnapshotWidget(
            self.database, self.icon_factory, self.button_factory
        )
        self.inspector_snapshot.day_navigated.connect(self._handle_day_navigated)
        self.inspector_snapshot.close_requested.connect(self._handle_inspector_closed)
        inspector_layout.addWidget(self.inspector_snapshot)

        self.workspace_layout.addWidget(self.rail_container, 6)
        self.workspace_layout.addWidget(self.inspector_container, 4)

        root_layout.addWidget(self.workspace)

    def load_history(self):
        """Reload all daily history rows from SQLite and populate the chronological rail."""
        self.history_rows = self.database.get_daily_history()
        self.dates_list = [row[1] for row in self.history_rows]

        self.clear_entries()
        self.history_cards.clear()

        has_rows = bool(self.history_rows)
        self.rail_scroll.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

        if not has_rows:
            self.inspector_container.setVisible(False)
            self.rail_container.setVisible(True)
            return

        # Group rows by recency
        current_group = None
        for row in self.history_rows:
            entry_date = row[1]
            focus_mins = row[2]
            completed = row[3]
            total = row[4]
            goal_met = bool(row[5])

            group_name = get_recency_group(entry_date)
            if group_name != current_group:
                current_group = group_name
                header_lbl = QLabel(current_group)
                header_lbl.setObjectName("HistoryWeekHeader")
                header_lbl.setContentsMargins(0, Spacing.SM, 0, Spacing.XS)
                self.entries_layout.addWidget(header_lbl)

            card = HistoryDayCard(
                entry_date=entry_date,
                focus_minutes=focus_mins,
                completed=completed,
                total=total,
                goal_met=goal_met,
                icon_factory=self.icon_factory,
            )
            card.clicked.connect(self.select_day)
            self.entries_layout.addWidget(card)
            self.history_cards[entry_date] = card

        self.entries_layout.addStretch()

        # Update responsive layout view
        self._update_responsive_view()

        # Default select latest date or preserve current selection
        target_date = self.selected_date if self.selected_date in self.history_cards else self.dates_list[0]
        self.select_day(target_date)

    def select_day(self, iso_date_str):
        """Select a date in the rail and update the Day Snapshot Inspector."""
        if iso_date_str not in self.history_cards:
            return

        self.selected_date = iso_date_str
        for d_str, card in self.history_cards.items():
            card.set_selected(d_str == iso_date_str)

        details = self.database.get_day_details(iso_date_str)
        curr_idx = self.dates_list.index(iso_date_str)
        has_prev = curr_idx < len(self.dates_list) - 1
        has_next = curr_idx > 0

        self.inspector_snapshot.set_day_details(details, has_prev=has_prev, has_next=has_next)

        # Handle responsive layout display
        if self.width() < self.COMPACT_BREAKPOINT:
            self.inspector_snapshot.set_compact_mode(True)
            self.rail_container.setVisible(False)
            self.inspector_container.setVisible(True)
        else:
            self.inspector_snapshot.set_compact_mode(False)
            self.rail_container.setVisible(True)
            self.inspector_container.setVisible(True)

    def _handle_inspector_closed(self):
        """When close button (✕) is clicked in compact mode, return to rail view."""
        if self.width() < self.COMPACT_BREAKPOINT:
            self.inspector_container.setVisible(False)
            self.rail_container.setVisible(True)

    def _handle_day_navigated(self, direction):
        if not self.selected_date or self.selected_date not in self.dates_list:
            return
        curr_idx = self.dates_list.index(self.selected_date)
        if direction == "prev" and curr_idx < len(self.dates_list) - 1:
            self.select_day(self.dates_list[curr_idx + 1])
        elif direction == "next" and curr_idx > 0:
            self.select_day(self.dates_list[curr_idx - 1])

    def _update_responsive_view(self):
        has_data = bool(self.history_rows)
        if not has_data:
            self.inspector_container.setVisible(False)
            self.rail_container.setVisible(True)
            return

        if self.width() >= self.COMPACT_BREAKPOINT:
            self.inspector_snapshot.set_compact_mode(False)
            self.rail_container.setVisible(True)
            self.inspector_container.setVisible(True)
        else:
            self.inspector_snapshot.set_compact_mode(True)
            # Default to rail visible if neither is visible
            if not self.inspector_container.isVisible():
                self.rail_container.setVisible(True)

    def clear_entries(self):
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_view()
