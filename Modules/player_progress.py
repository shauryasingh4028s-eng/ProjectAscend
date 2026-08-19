"""Project Ascend v1.5 Player Progress.

A compact, presentation-focused view over the progression service. Every
number and unlock comes from persisted productivity data; the character is a
2D visual representation of that progress, not a separate game system.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Modules.gamification_config import (
    ACHIEVEMENTS,
    CHARACTERS,
    EVOLUTION_STAGES,
    RANKS,
    XP_PER_LEVEL,
    xp_into_level,
)
from Modules.insights_service import format_day_count, format_minutes
from UI.components.character_sprites import CharacterSprite, character_pixmap
from UI.theme.design_system import Spacing


class ProgressStatCard(QFrame):
    """Compact metric tile reused across the progression grid."""

    def __init__(self, title, tint=None, tone=None):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(78)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            Spacing.MD,
            Spacing.SM + 2,
            Spacing.MD,
            Spacing.SM + 2,
        )
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


class AchievementCard(QFrame):
    """One compact, persistent achievement state."""

    def __init__(self, definition):
        super().__init__()
        self.definition = definition
        self.setObjectName("AchievementCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(92)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(Spacing.MD)

        self.symbol_label = QLabel(definition.symbol)
        self.symbol_label.setObjectName("AchievementSymbol")
        self.symbol_label.setAlignment(Qt.AlignCenter)
        self.symbol_label.setFixedSize(44, 44)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.name_label = QLabel(definition.name)
        self.name_label.setObjectName("AchievementName")
        self.description_label = QLabel(definition.description)
        self.description_label.setObjectName("MutedText")
        self.description_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setObjectName("AchievementStatus")
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.description_label)
        text_layout.addWidget(self.status_label)

        layout.addWidget(self.symbol_label, alignment=Qt.AlignTop)
        layout.addLayout(text_layout, 1)

    @staticmethod
    def _progress_text(state):
        definition = state.definition
        value = min(state.current_value, definition.threshold)
        if definition.metric == "focus_minutes":
            return f"{format_minutes(int(value))} / {format_minutes(definition.threshold)}"
        if definition.metric == "level":
            return f"Level {int(value)} / {definition.threshold}"
        return f"{int(value):,} / {definition.threshold:,}"

    def set_state(self, state):
        self.setProperty("unlocked", "true" if state.unlocked else "false")
        self.symbol_label.setProperty(
            "unlocked",
            "true" if state.unlocked else "false",
        )
        if state.unlocked:
            self.status_label.setText(f"Earned · {state.definition.category}")
        else:
            self.status_label.setText(self._progress_text(state))
        self.style().unpolish(self)
        self.style().polish(self)
        self.symbol_label.style().unpolish(self.symbol_label)
        self.symbol_label.style().polish(self.symbol_label)


class MilestoneRow(QFrame):
    """Broad progression track with a compact tier bar."""

    def __init__(self, track):
        super().__init__()
        self.track = track
        self.setObjectName("MilestoneRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(70)

        layout = QGridLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setHorizontalSpacing(Spacing.MD)
        layout.setVerticalSpacing(3)

        self.name_label = QLabel(track.name)
        self.name_label.setObjectName("AchievementName")
        self.tier_label = QLabel()
        self.tier_label.setObjectName("MilestoneTier")
        self.tier_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.description_label = QLabel(track.description)
        self.description_label.setObjectName("MutedText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("MilestoneBar")
        self.progress_bar.setTextVisible(False)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("AchievementStatus")
        self.progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(self.name_label, 0, 0)
        layout.addWidget(self.tier_label, 0, 1)
        layout.addWidget(self.description_label, 1, 0)
        layout.addWidget(self.progress_label, 1, 1)
        layout.addWidget(self.progress_bar, 2, 0, 1, 2)
        layout.setColumnStretch(0, 1)

    def _value_text(self, value):
        if self.track.unit == "minutes":
            return format_minutes(int(value))
        if self.track.unit == "levels":
            return f"Level {int(value)}"
        if self.track.unit == "days":
            return format_day_count(value)
        return f"{int(value):,} {self.track.unit}"

    def set_state(self, state):
        tier_total = len(state.track.thresholds)
        self.tier_label.setText(f"Tier {state.completed_tiers} / {tier_total}")
        if state.next_threshold is None:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.progress_label.setText("All tiers reached")
            return

        previous = (
            state.track.thresholds[state.completed_tiers - 1]
            if state.completed_tiers
            else 0
        )
        current = max(previous, min(state.current_value, state.next_threshold))
        self.progress_bar.setRange(int(previous), int(state.next_threshold))
        self.progress_bar.setValue(int(current))
        self.progress_label.setText(
            f"{self._value_text(state.current_value)} · next {self._value_text(state.next_threshold)}"
        )


class PlayerProgressPage(QWidget):
    """Information-dense home for productivity progression."""

    character_changed = Signal(str)

    def __init__(self, progression_service, character_manager):
        super().__init__()
        self.progression_service = progression_service
        self.character_manager = character_manager
        self.open_animation = None
        self.character_buttons = {}
        self.build_ui()
        self.refresh()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(
            Spacing.XXL,
            Spacing.LG,
            Spacing.XXL,
            Spacing.XXL,
        )
        self.content_layout.setSpacing(Spacing.LG)

        self.content_layout.addWidget(self.create_character_card())
        self.content_layout.addWidget(self.create_stats_section())
        self.content_layout.addWidget(self.create_achievements_section())
        self.content_layout.addWidget(self.create_milestones_section())
        self.content_layout.addWidget(self.create_level_progression_section())
        self.content_layout.addWidget(self.create_character_selection_section())
        self.content_layout.addStretch()

        self.scroll_area.setWidget(content)
        root_layout.addWidget(self.scroll_area)

    def create_character_card(self):
        self.hero_card = QFrame()
        self.hero_card.setObjectName("ProgressHeroCard")
        self.hero_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hero_card.setMinimumHeight(210)

        layout = QHBoxLayout(self.hero_card)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.XL, Spacing.MD)
        layout.setSpacing(Spacing.XL)

        character_column = QVBoxLayout()
        character_column.setSpacing(0)
        self.character_sprite = CharacterSprite()
        self.character_sprite.setFixedSize(170, 170)
        self.character_name_label = QLabel()
        self.character_name_label.setObjectName("CharacterName")
        self.character_name_label.setAlignment(Qt.AlignCenter)
        self.evolution_label = QLabel()
        self.evolution_label.setObjectName("MutedText")
        self.evolution_label.setAlignment(Qt.AlignCenter)
        character_column.addWidget(self.character_sprite, alignment=Qt.AlignCenter)
        character_column.addWidget(self.character_name_label)
        character_column.addWidget(self.evolution_label)

        details = QVBoxLayout()
        details.setSpacing(Spacing.XS + 2)
        self.rank_label = QLabel()
        self.rank_label.setObjectName("PlayerRank")
        self.level_title = QLabel("Level 1")
        self.level_title.setObjectName("ProgressLevel")
        self.total_xp_label = QLabel("0 XP earned in total")
        self.total_xp_label.setObjectName("MutedText")

        self.level_bar = QProgressBar()
        self.level_bar.setObjectName("XpBar")
        self.level_bar.setTextVisible(False)
        self.level_bar.setRange(0, XP_PER_LEVEL)
        self.next_level_label = QLabel()
        self.next_level_label.setObjectName("MutedText")

        streak_row = QHBoxLayout()
        streak_row.setSpacing(Spacing.SM)
        self.hero_current_streak = self._compact_metric(
            "Current streak",
            "amber",
        )
        self.hero_best_streak = self._compact_metric("Best streak", "blue")
        streak_row.addWidget(self.hero_current_streak[0], 1)
        streak_row.addWidget(self.hero_best_streak[0], 1)

        details.addWidget(self.rank_label)
        details.addWidget(self.level_title)
        details.addWidget(self.total_xp_label)
        details.addWidget(self.level_bar)
        details.addWidget(self.next_level_label)
        details.addSpacing(Spacing.XS)
        details.addLayout(streak_row)
        details.addStretch()

        layout.addLayout(character_column)
        layout.addLayout(details, 1)
        return self.hero_card

    @staticmethod
    def _compact_metric(title, tint):
        frame = QFrame()
        frame.setObjectName("CompactStatRow")
        frame.setProperty("tint", tint)
        frame.setMinimumHeight(50)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
        layout.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("InsightMetricTitle")
        value_label = QLabel("0 days")
        value_label.setObjectName("CompactStatValue")
        value_label.setProperty("tone", tint)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, value_label

    def _section(self, title, description=""):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(
            Spacing.LG,
            Spacing.MD + 2,
            Spacing.LG,
            Spacing.LG,
        )
        layout.setSpacing(Spacing.MD)

        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        heading.addWidget(title_label)
        heading.addStretch()
        layout.addLayout(heading)
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("MutedText")
            description_label.setWordWrap(True)
            layout.addWidget(description_label)
        return section, layout, heading

    def create_stats_section(self):
        section, layout, _heading = self._section(
            "Productivity Progress",
            "Verified all-time work and daily-goal consistency.",
        )
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
            "focus_time": ProgressStatCard(
                "Focus Time", tint="blue", tone="blue"
            ),
            "completed_activities": ProgressStatCard(
                "Activities Completed", tint="green", tone="green"
            ),
            "goal_days": ProgressStatCard(
                "Daily Goals Met", tint="green", tone="green"
            ),
            "completion": ProgressStatCard(
                "Goal Success", tint="purple", tone="purple"
            ),
        }
        for index, card in enumerate(self.stat_cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        return section

    def create_achievements_section(self):
        section, layout, heading = self._section(
            "Achievements",
            "Meaningful accomplishments stay earned once unlocked.",
        )
        self.achievement_summary_label = QLabel()
        self.achievement_summary_label.setObjectName("Badge")
        heading.addWidget(self.achievement_summary_label)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.SM)
        self.achievement_cards = {}
        for index, definition in enumerate(ACHIEVEMENTS):
            card = AchievementCard(definition)
            self.achievement_cards[definition.identifier] = card
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return section

    def create_milestones_section(self):
        section, layout, _heading = self._section(
            "Milestones",
            "Broader tracks show how sustained productivity accumulates.",
        )
        self.milestone_rows = {}
        # The service snapshot provides rows in the same declarative order.
        from Modules.gamification_config import MILESTONE_TRACKS

        for track in MILESTONE_TRACKS:
            row = MilestoneRow(track)
            self.milestone_rows[track.identifier] = row
            layout.addWidget(row)
        return section

    def create_level_progression_section(self):
        section, layout, _heading = self._section(
            "Level Progression",
            "Named ranks are configured centrally while the established level curve remains intact.",
        )
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.SM)
        self.rank_cards = []
        for index, rank in enumerate(RANKS):
            card = QFrame()
            card.setObjectName("RankCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(
                Spacing.MD,
                Spacing.SM,
                Spacing.MD,
                Spacing.SM,
            )
            card_layout.setSpacing(2)
            name = QLabel(rank.name)
            name.setObjectName("AchievementName")
            threshold = QLabel(f"From Level {rank.minimum_level}")
            threshold.setObjectName("MutedText")
            card_layout.addWidget(name)
            card_layout.addWidget(threshold)
            grid.addWidget(card, index // 3, index % 3)
            self.rank_cards.append((rank, card))
        for column in range(3):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        return section

    def create_character_selection_section(self):
        section, layout, _heading = self._section(
            "Character",
            "Choose an original 2D character to represent your progress. Basic selection is always available.",
        )
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.SM)
        self.character_button_group = QButtonGroup(self)
        self.character_button_group.setExclusive(True)

        for index, character in enumerate(CHARACTERS):
            button = QPushButton(character.name)
            button.setObjectName("CharacterChoice")
            button.setCheckable(True)
            button.setMinimumHeight(82)
            button.setIconSize(character_pixmap(character, "stage_1", 58).size())
            button.clicked.connect(
                lambda _checked=False, identifier=character.identifier: self.select_character(identifier)
            )
            self.character_button_group.addButton(button)
            self.character_buttons[character.identifier] = button
            grid.addWidget(button, index // 4, index % 4)

        for column in range(4):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        return section

    def select_character(self, character_id):
        if self.character_manager.select(character_id):
            self.character_changed.emit(character_id)
        self.refresh()

    def refresh_character_icons(self, stage_identifier="stage_1"):
        for character in CHARACTERS:
            button = self.character_buttons[character.identifier]
            pixmap = character_pixmap(character, stage_identifier, 58)
            button.setIcon(QIcon(pixmap))
            button.setIconSize(pixmap.size())

    def refresh(self):
        """Re-read persisted progression and update every visible value."""
        snapshot = self.progression_service.snapshot()
        metrics = snapshot.metrics
        level_xp = xp_into_level(metrics.total_xp)
        xp_remaining = XP_PER_LEVEL - level_xp

        self.character_sprite.set_character(
            snapshot.character.identifier,
            snapshot.evolution_stage.identifier,
        )
        self.character_name_label.setText(snapshot.character.name)
        stage_index = EVOLUTION_STAGES.index(snapshot.evolution_stage) + 1
        self.evolution_label.setText(
            f"Evolution stage {stage_index} of {len(EVOLUTION_STAGES)}"
        )
        self.rank_label.setText(snapshot.rank.name.upper())
        self.level_title.setText(f"Level {metrics.level}")
        self.total_xp_label.setText(f"{metrics.total_xp:,} XP earned in total")
        self.level_bar.setValue(level_xp)
        self.next_level_label.setText(
            f"{level_xp} / {XP_PER_LEVEL} XP  ·  "
            f"{xp_remaining} XP to Level {metrics.level + 1}"
        )
        self.hero_current_streak[1].setText(
            format_day_count(metrics.current_streak)
        )
        self.hero_best_streak[1].setText(format_day_count(metrics.best_streak))

        self.stat_cards["current_streak"].set_value(
            format_day_count(metrics.current_streak),
            "Consecutive daily goals",
        )
        self.stat_cards["best_streak"].set_value(
            format_day_count(metrics.best_streak),
            "Personal record",
        )
        self.stat_cards["focus_time"].set_value(
            format_minutes(metrics.focus_minutes),
            "Completed focused work",
        )
        self.stat_cards["completed_activities"].set_value(
            f"{metrics.completed_activities:,}",
            "Finished activities",
        )
        self.stat_cards["goal_days"].set_value(
            format_day_count(metrics.goal_days),
            "Total days goal met",
        )
        self.stat_cards["completion"].set_value(
            f"{metrics.goal_completion_rate:g}%",
            "Of recorded activity days",
        )

        unlocked_count = sum(1 for state in snapshot.achievements if state.unlocked)
        self.achievement_summary_label.setText(
            f"{unlocked_count} of {len(snapshot.achievements)} earned"
        )
        for state in snapshot.achievements:
            self.achievement_cards[state.definition.identifier].set_state(state)

        for state in snapshot.milestones:
            self.milestone_rows[state.track.identifier].set_state(state)

        for rank, card in self.rank_cards:
            active = rank == snapshot.rank
            card.setProperty("active", "true" if active else "false")
            card.style().unpolish(card)
            card.style().polish(card)

        selected_id = snapshot.character.identifier
        for identifier, button in self.character_buttons.items():
            button.setChecked(identifier == selected_id)
        self.refresh_character_icons(snapshot.evolution_stage.identifier)

    def animate_open(self):
        """Very subtle Player Progress entrance (Tier 1, 420 ms)."""
        if self.open_animation is not None:
            self.open_animation.stop()
        effect = self.hero_card.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.hero_card)
            self.hero_card.setGraphicsEffect(effect)
        # Keep information immediately readable; the entrance is polish, not
        # a loading state.
        effect.setOpacity(0.65)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(420)
        animation.setStartValue(0.65)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self.open_animation = animation
        animation.start()
