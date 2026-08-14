"""Player Progress page.

Presentation-only. Every value shown here is read from the existing
XPManager and StreakManager; this module defines no XP formula, no level
curve and no progression rules of its own.
"""

from PySide6.QtCore import Qt
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

from Modules.insights_service import format_day_count
from UI.theme.design_system import Spacing, Typography

# Mirrors XPManager.get_level(): one level per 100 XP.
XP_PER_LEVEL = 100


class ProgressStatCard(QFrame):
    """Compact metric tile reused across the progression grid.

    ``tint``/``tone`` give each progression metric a semantic identity
    (amber = current streak, blue = best streak, green = goal days,
    purple = completion intelligence) through the shared stylesheet.
    """

    def __init__(self, title, tint=None, tone=None):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(78)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM + 2, Spacing.MD, Spacing.SM + 2)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("InsightMetricTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("InsightMetricValue")
        if tone:
            self.value_label.setProperty("tone", tone)
        self.note_label = QLabel()
        self.note_label.setObjectName("InsightMetricNote")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_value(self, value, note=""):
        self.value_label.setText(value)
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))


class PlayerProgressPage(QWidget):
    """Shows the existing level, XP and streak mechanics in one place."""

    def __init__(self, xp_manager, streak_manager):
        super().__init__()
        self.xp_manager = xp_manager
        self.streak_manager = streak_manager

        self.build_ui()
        self.refresh()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(Spacing.XXL, Spacing.XL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.LG)

        layout.addWidget(self.create_level_card())
        layout.addWidget(self.create_stats_section())
        layout.addStretch()

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def create_level_card(self):
        card = QFrame()
        card.setObjectName("HeroCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        layout.setSpacing(Spacing.XL)

        # Progression speaks purple: level badge, XP bar and values carry
        # the intelligence identity across both themes. Styled by the
        # shared stylesheet so the badge follows theme switches.
        self.level_badge = QLabel("1")
        self.level_badge.setObjectName("LevelBadge")
        self.level_badge.setAlignment(Qt.AlignCenter)
        self.level_badge.setFixedSize(64, 64)

        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(Spacing.XS + 2)

        self.level_title = QLabel("Level 1")
        self.level_title.setObjectName("Greeting")
        self.total_xp_label = QLabel("0 XP earned in total")
        self.total_xp_label.setObjectName("MutedText")

        self.level_bar = QProgressBar()
        self.level_bar.setObjectName("XpBar")
        self.level_bar.setTextVisible(False)
        self.level_bar.setRange(0, XP_PER_LEVEL)

        self.next_level_label = QLabel()
        self.next_level_label.setObjectName("MutedText")

        detail_layout.addWidget(self.level_title)
        detail_layout.addWidget(self.total_xp_label)
        detail_layout.addWidget(self.level_bar)
        detail_layout.addWidget(self.next_level_label)

        layout.addWidget(self.level_badge, alignment=Qt.AlignTop)
        layout.addLayout(detail_layout, 1)
        return card

    def create_stats_section(self):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(section)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        title = QLabel("Progression")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.MD)

        self.stat_cards = {
            "current_streak": ProgressStatCard(
                "Current Streak", tint="amber", tone="amber"
            ),
            "best_streak": ProgressStatCard(
                "Best Streak", tint="blue", tone="blue"
            ),
            "goal_days": ProgressStatCard(
                "Daily Goals Met", tint="green", tone="green"
            ),
            "completion": ProgressStatCard(
                "Goal Completion Rate", tint="purple", tone="purple"
            ),
        }
        for column, card in enumerate(self.stat_cards.values()):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)

        layout.addLayout(grid)

        note = QLabel(
            "Complete activities to earn XP. Meeting your daily focus goal "
            "extends your streak."
        )
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        layout.addWidget(note)
        return section

    def refresh(self):
        """Re-read the persisted progression values and update the page."""
        total_xp = self.xp_manager.get_total_xp()
        level = self.xp_manager.get_level()
        xp_into_level = total_xp % XP_PER_LEVEL
        xp_remaining = XP_PER_LEVEL - xp_into_level

        self.level_badge.setText(str(level))
        self.level_title.setText(f"Level {level}")
        self.total_xp_label.setText(f"{total_xp:,} XP earned in total")
        self.level_bar.setValue(xp_into_level)
        self.next_level_label.setText(
            f"{xp_into_level} / {XP_PER_LEVEL} XP  •  "
            f"{xp_remaining} XP to Level {level + 1}"
        )

        current_streak = self.streak_manager.get_current_streak()
        best_streak = self.streak_manager.get_longest_streak()
        goal_days = self.streak_manager.get_total_goal_days()
        completion_rate = self.streak_manager.get_completion_rate()

        self.stat_cards["current_streak"].set_value(
            format_day_count(current_streak),
            "Consecutive daily goals",
        )
        self.stat_cards["best_streak"].set_value(
            format_day_count(best_streak),
            "Personal record",
        )
        self.stat_cards["goal_days"].set_value(
            format_day_count(goal_days),
            "Total days goal met",
        )
        self.stat_cards["completion"].set_value(
            f"{completion_rate}%",
            "Of all recorded days",
        )
