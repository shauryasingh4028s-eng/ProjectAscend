from datetime import datetime

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Modules.date_utils import format_display_date
from UI.theme.design_system import Colors, ThemeManager


class CardFrame(QFrame):
    def __init__(self, object_name, shadow=True):
        super().__init__()
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        if shadow:
            ThemeManager.add_shadow(self)


def make_label(text, object_name=None, alignment=None):
    label = QLabel(text)

    if object_name is not None:
        label.setObjectName(object_name)

    if alignment is not None:
        label.setAlignment(alignment)

    return label


class StatTile(CardFrame):
    """Metric tile with an optional semantic identity.

    ``tone`` (blue / green / purple / amber / None) tints the tile's
    background softly and colours its icon and value strongly, so every
    metric carries a meaning at a glance. Icons are re-rendered from the
    active theme on refresh.
    """

    TONE_ICON_COLORS = {
        "blue": Colors.PRIMARY,
        "green": Colors.SUCCESS,
        "purple": Colors.ACCENT,
        "amber": Colors.WARNING,
    }

    def __init__(self, icon_name, title, value_label, tone=None, icon_factory=None):
        super().__init__("StatTile")
        self.setMinimumHeight(82)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.icon_name = icon_name
        self.tone = tone
        self.icon_factory = icon_factory

        if tone:
            self.setProperty("tint", tone)
            value_label.setProperty("tone", tone)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)

        title_label = make_label(title, "StatTitle")

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        value_label.setObjectName("StatValue")
        value_label.setWordWrap(False)
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value_label.setMinimumHeight(30)

        layout.addLayout(header_layout)
        layout.addWidget(value_label)
        self.setLayout(layout)

        self.refresh_icon()

    def refresh_icon(self):
        if self.icon_factory is None:
            return
        color = self.TONE_ICON_COLORS.get(self.tone, Colors.TEXT_SECONDARY)
        icon = self.icon_factory.get(self.icon_name, color)
        self.icon_label.setPixmap(icon.pixmap(QSize(18, 18)))


class CompactStatRow(QFrame):
    """Compact statistic row with the same optional semantic identity."""

    TONE_ICON_COLORS = StatTile.TONE_ICON_COLORS

    def __init__(self, icon_name, title, value_label, tone=None, icon_factory=None):
        super().__init__()
        self.setObjectName("CompactStatRow")
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.icon_name = icon_name
        self.tone = tone
        self.icon_factory = icon_factory

        if tone:
            self.setProperty("tint", tone)
            value_label.setProperty("tone", tone)

        layout = QHBoxLayout()
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setAlignment(Qt.AlignCenter)

        title_label = make_label(title, "StatTitle")
        value_label.setObjectName("CompactStatValue")
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.icon_label)
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(value_label)
        self.setLayout(layout)

        self.refresh_icon()

    def refresh_icon(self):
        if self.icon_factory is None:
            return
        color = self.TONE_ICON_COLORS.get(self.tone, Colors.TEXT_SECONDARY)
        icon = self.icon_factory.get(self.icon_name, color)
        self.icon_label.setPixmap(icon.pixmap(QSize(16, 16)))


class HeroCard(CardFrame):
    """Greeting bar: who the user is today, and what day it is.

    The page title lives in the shell header, so this card stays a compact
    context strip rather than repeating it.
    """

    def __init__(self, settings_button, greeting):
        super().__init__("HeroCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(74)

        layout = QHBoxLayout()
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        greeting_label = make_label(f"{greeting}, Ascender", "Greeting")
        quote = make_label("Stay focused. Keep ascending.", "MutedText")

        text_layout.addWidget(greeting_label)
        text_layout.addWidget(quote)

        date_layout = QVBoxLayout()
        date_layout.setSpacing(1)
        now = datetime.now()
        date_label = make_label(
            format_display_date(now.date()),
            "CompactStatValue",
            Qt.AlignRight | Qt.AlignVCenter,
        )
        weekday_label = make_label(
            now.strftime("%A"),
            "MutedText",
            Qt.AlignRight | Qt.AlignVCenter,
        )
        date_layout.addWidget(date_label)
        date_layout.addWidget(weekday_label)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addLayout(date_layout)
        self.setLayout(layout)


class ProgressCard(CardFrame):
    def __init__(self, icon_factory):
        super().__init__("MetricCard")
        self.icon_factory = icon_factory
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.daily_goal_label = QLabel()
        self.progress_bar = QProgressBar()
        self.study_time_label = QLabel("0h 0m")
        self.completed_total_label = QLabel("0 / 0")
        self.remaining_minutes_label = QLabel("0h 0m")

        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title = make_label("Today's Progress", "SectionTitle")
        self.daily_goal_label.setObjectName("MutedText")
        self.daily_goal_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.daily_goal_label)

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMinimumHeight(10)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setContentsMargins(0, 0, 0, 0)

        # Three semantic metric zones: focus (blue), completed (green),
        # remaining (purple). Soft backgrounds + strong values + matching
        # icons make each metric's meaning obvious without extra words.
        self.focus_tile = StatTile(
            "fa5s.clock",
            "Focus Time",
            self.study_time_label,
            tone="blue",
            icon_factory=self.icon_factory,
        )
        self.completed_tile = StatTile(
            "fa5s.check-circle",
            "Completed",
            self.completed_total_label,
            tone="green",
            icon_factory=self.icon_factory,
        )
        self.remaining_tile = StatTile(
            "fa5s.bullseye",
            "Remaining",
            self.remaining_minutes_label,
            tone="purple",
            icon_factory=self.icon_factory,
        )

        stats_grid.addWidget(self.focus_tile, 0, 0)
        stats_grid.addWidget(self.completed_tile, 0, 1)
        stats_grid.addWidget(self.remaining_tile, 0, 2)

        for column in range(3):
            stats_grid.setColumnStretch(column, 1)

        layout.addLayout(header_layout)
        layout.addWidget(self.progress_bar)
        layout.addLayout(stats_grid)
        self.setLayout(layout)

    def refresh_semantic_icons(self):
        """Re-render the metric icons with the active theme's colours."""
        for tile in (
            self.focus_tile,
            self.completed_tile,
            self.remaining_tile,
        ):
            tile.refresh_icon()


class PlayerCard(CardFrame):
    def __init__(self, icon_factory):
        super().__init__("PlayerCard")
        self.icon_factory = icon_factory
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.level_label = QLabel("Level 1")
        self.current_xp_label = QLabel("0 XP")
        self.xp_bar = QProgressBar()
        self.current_streak_label = QLabel("0 days")
        self.best_streak_label = QLabel("0 days")

        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)

        title = make_label("Player Progress", "SectionTitle")

        self.level_label.setObjectName("PlayerLevel")
        self.level_label.setMinimumHeight(26)

        self.current_xp_label.setObjectName("PlayerXp")
        self.current_xp_label.setMinimumHeight(18)

        self.xp_bar.setObjectName("XpBar")
        self.xp_bar.setRange(0, 100)
        self.xp_bar.setValue(0)
        self.xp_bar.setMinimumHeight(10)
        self.xp_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        streak_layout = QVBoxLayout()
        streak_layout.setContentsMargins(0, 2, 0, 0)
        streak_layout.setSpacing(6)
        # Streak rows carry attention (amber) and achievement (blue)
        # identities; XP and level speak purple via the stylesheet.
        self.current_streak_row = CompactStatRow(
            "fa5s.fire",
            "Current Streak",
            self.current_streak_label,
            tone="amber",
            icon_factory=self.icon_factory,
        )
        self.best_streak_row = CompactStatRow(
            "fa5s.trophy",
            "Best Streak",
            self.best_streak_label,
            tone="blue",
            icon_factory=self.icon_factory,
        )
        streak_layout.addWidget(self.current_streak_row)
        streak_layout.addWidget(self.best_streak_row)

        layout.addWidget(title)
        layout.addWidget(self.level_label)
        layout.addWidget(self.current_xp_label)
        layout.addWidget(self.xp_bar)
        layout.addLayout(streak_layout)
        self.setLayout(layout)

    def refresh_semantic_icons(self):
        """Re-render the streak icons with the active theme's colours."""
        self.current_streak_row.refresh_icon()
        self.best_streak_row.refresh_icon()


class FocusCard(CardFrame):
    def __init__(self, start_button, pause_button, complete_button):
        super().__init__("FocusCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.current_activity_label = make_label("Current Activity: Ready", "MutedText")
        self.timer_label = make_label("00:00:00", "Timer", Qt.AlignCenter)
        self.timer_label.setMinimumWidth(300)
        self.build_ui(start_button, pause_button, complete_button)

    def build_ui(self, start_button, pause_button, complete_button):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(20)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.addWidget(make_label("Focus Session", "SectionTitle"))
        left_layout.addWidget(self.current_activity_label)
        left_layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addWidget(start_button)
        button_layout.addWidget(pause_button)
        button_layout.addWidget(complete_button)

        layout.addLayout(left_layout, 2)
        layout.addWidget(self.timer_label, 2)
        layout.addLayout(button_layout, 2)
        self.setLayout(layout)


class ActivityCard(CardFrame):
    selected = Signal(int)
    menu_requested = Signal(int, object)
    double_clicked = Signal(int)

    def __init__(self, activity, icon_factory, overflow_button):
        super().__init__("ActivityCard", shadow=False)
        self.activity = activity
        self.icon_factory = icon_factory
        self.overflow_button = overflow_button
        self.setProperty("selected", False)
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.installEventFilter(self)
        self.build_ui()

    def build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(12)

        icon_name = "fa5s.check-circle" if self.activity.completed else "fa5s.circle"
        status_icon = QLabel()
        status_icon.setFixedSize(24, 24)
        status_icon.setAlignment(Qt.AlignCenter)
        status_icon.setPixmap(self.icon_factory.get(icon_name).pixmap(22, 22))

        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)

        name_label = QLabel(self.activity.name)
        name_label.setStyleSheet("font-size: 16px; font-weight: 750;")
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        type_badge = QLabel(self.activity.activity_type)
        type_badge.setObjectName("Badge")
        type_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        text_layout.addWidget(name_label)
        text_layout.addWidget(type_badge)

        time_layout = QGridLayout()
        time_layout.setHorizontalSpacing(24)
        time_layout.setVerticalSpacing(5)

        estimated_title = QLabel("Estimated")
        estimated_title.setObjectName("StatTitle")
        actual_title = QLabel("Actual")
        actual_title.setObjectName("StatTitle")

        estimated_value = QLabel(f"{self.activity.estimated_minutes} min")
        estimated_value.setStyleSheet("font-size: 15px; font-weight: 700;")
        actual_value = QLabel(f"{self.activity.actual_minutes} min")
        actual_value.setStyleSheet("font-size: 15px; font-weight: 700;")

        time_layout.addWidget(estimated_title, 0, 0)
        time_layout.addWidget(actual_title, 0, 1)
        time_layout.addWidget(estimated_value, 1, 0)
        time_layout.addWidget(actual_value, 1, 1)

        badge_text = "Completed" if self.activity.completed else "Planned"
        completion_badge = QLabel(badge_text)
        completion_badge.setObjectName(
            "CompletedBadge" if self.activity.completed else "PlannedBadge"
        )
        completion_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        self.overflow_button.clicked.connect(self.emit_menu_request)

        layout.addWidget(status_icon)
        layout.addLayout(text_layout, 4)
        layout.addStretch(1)
        layout.addLayout(time_layout, 2)
        layout.addWidget(completion_badge)
        layout.addWidget(self.overflow_button)
        self.setLayout(layout)

    def emit_menu_request(self):
        position = self.overflow_button.mapToGlobal(
            self.overflow_button.rect().bottomLeft()
        )
        self.menu_requested.emit(self.activity.id, position)

    def set_selected(self, is_selected):
        self.setProperty("selected", is_selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def eventFilter(self, watched, event):
        if watched is self and event.type() == QEvent.MouseButtonPress:
            self.selected.emit(self.activity.id)
            return False

        if watched is self and event.type() == QEvent.MouseButtonDblClick:
            self.double_clicked.emit(self.activity.id)
            return True

        return super().eventFilter(watched, event)


class EmptyActivityState(QWidget):
    def __init__(self, text):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        # Themed via the shared stylesheet so the empty state reads
        # correctly in both light and dark.
        icon = QLabel("+")
        icon.setObjectName("EmptyStateIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(54, 54)

        title = QLabel("No activities planned")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)

        description = QLabel(text)
        description.setObjectName("MutedText")
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        description.setMaximumWidth(420)

        cta = QLabel("Use Add Activity to start building today's plan.")
        cta.setObjectName("MutedText")
        cta.setAlignment(Qt.AlignCenter)

        layout.addWidget(icon, alignment=Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(cta)
        self.setLayout(layout)


class ActivitySection(CardFrame):
    activity_selected = Signal(int)
    activity_double_clicked = Signal(int)
    activity_menu_requested = Signal(int, object)

    def __init__(self):
        super().__init__("ActivitySection")
        self.cards = {}
        self.selected_activity_id = None
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = make_label("Today's Activities", "SectionTitle")
        subtitle = make_label("Select a task to begin a focused session.", "MutedText")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.content_layout.addStretch()
        self.content.setLayout(self.content_layout)

        scroll_area.setWidget(self.content)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(scroll_area, 1)
        self.setLayout(layout)

    def clear_cards(self):
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self.cards = {}
        self.selected_activity_id = None
        self.content_layout.addStretch()

    def add_empty_state(self, text):
        self.clear_cards()
        self.content_layout.insertWidget(0, EmptyActivityState(text), 1)

    def add_activity_card(self, activity_id, card):
        stretch_item = self.content_layout.takeAt(self.content_layout.count() - 1)
        self.cards[activity_id] = card
        card.selected.connect(self.select_activity)
        card.double_clicked.connect(self.activity_double_clicked.emit)
        card.menu_requested.connect(self.activity_menu_requested.emit)
        self.content_layout.addWidget(card)
        self.content_layout.addItem(stretch_item)

    def select_activity(self, activity_id):
        self.selected_activity_id = activity_id

        for card_id, card in self.cards.items():
            card.set_selected(card_id == activity_id)

        self.activity_selected.emit(activity_id)


class ActionBar(CardFrame):
    def __init__(self, add_button, plan_button, insights_button):
        super().__init__("ActionBar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        title = make_label("Quick Actions", "SectionTitle")

        for button in (add_button, plan_button, insights_button):
            button.setMinimumHeight(40)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setCursor(Qt.PointingHandCursor)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(add_button)
        layout.addWidget(plan_button)
        layout.addWidget(insights_button)
        self.setLayout(layout)
