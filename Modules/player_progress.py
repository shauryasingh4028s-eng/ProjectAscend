"""Project Ascend v1.5 Player Progress presentation.

The page is a compact progression centre over the existing, persisted
progression snapshot.  It contains no XP, rank, achievement, milestone,
streak or evolution business logic.
"""

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Modules.gamification_config import (
    ACHIEVEMENTS,
    CHARACTERS,
    EVOLUTION_STAGES,
    MILESTONE_TRACKS,
    RANKS,
    XP_PER_LEVEL,
    xp_into_level,
)
from Modules.insights_service import format_day_count, format_minutes
from UI.components.character_sprites import CharacterSprite, character_pixmap
from UI.theme.design_system import (
    ButtonFactory,
    Colors,
    IconFactory,
    Spacing,
)


FEATURED_ACHIEVEMENT_LIMIT = 4


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _achievement_progress_ratio(state):
    threshold = max(1, state.definition.threshold)
    return min(1.0, max(0.0, float(state.current_value) / threshold))


def featured_achievement_states(states, limit=FEATURED_ACHIEVEMENT_LIMIT):
    """Select recent earned work, then the closest meaningful locked work."""
    indexed = list(enumerate(states))
    unlocked = sorted(
        ((index, state) for index, state in indexed if state.unlocked),
        key=lambda pair: (pair[1].unlocked_at or "", -pair[0]),
        reverse=True,
    )
    locked = sorted(
        ((index, state) for index, state in indexed if not state.unlocked),
        key=lambda pair: (-_achievement_progress_ratio(pair[1]), pair[0]),
    )

    # A brand-new user should see approachable first steps, not distant level
    # goals merely because Level 1 produces a non-zero ratio.
    has_productivity_progress = any(
        state.current_value > 0 and state.definition.metric != "level"
        for _index, state in locked
    )
    if not unlocked and not has_productivity_progress:
        return tuple(state for _index, state in indexed[:limit])

    selected = [state for _index, state in unlocked[:2]]
    selected.extend(
        state for _index, state in locked[: max(0, limit - len(selected))]
    )
    if len(selected) < limit:
        selected.extend(
            state for _index, state in unlocked[2 : 2 + limit - len(selected)]
        )
    return tuple(selected[:limit])


def _format_unlock_date(timestamp):
    if not timestamp:
        return "Earned"
    try:
        value = datetime.fromisoformat(timestamp)
        return f"Earned · {value.strftime('%d %b %Y')}"
    except (TypeError, ValueError):
        return "Earned"


class ProgressStatCard(QFrame):
    """One compact verified productivity statistic inside the hero."""

    def __init__(self, title, tint=None, tone=None):
        super().__init__()
        self.setObjectName("HeroStat")
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
        layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("HeroStatTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("HeroStatValue")
        if tone:
            self.value_label.setProperty("tone", tone)
        self.note_label = QLabel()
        self.note_label.setVisible(False)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value, note=""):
        self.value_label.setText(value)
        self.note_label.setText(note)


class RankProgressWidget(QWidget):
    """Compact CURRENT → NEXT → FUTURE rank path integrated into the hero."""

    def __init__(self):
        super().__init__()
        self.current_level = 1
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_level(self, level):
        self.current_level = max(1, int(level))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        count = len(RANKS)
        if count < 2:
            return
        margin = 48
        width = max(1, self.width() - margin * 2)
        points = [margin + width * index / (count - 1) for index in range(count)]
        current_index = max(
            index
            for index, rank in enumerate(RANKS)
            if rank.minimum_level <= self.current_level
        )

        line_y = 16
        painter.setPen(QPen(QColor(Colors.BORDER_STRONG), 2))
        painter.drawLine(int(points[0]), line_y, int(points[-1]), line_y)
        if current_index:
            painter.setPen(QPen(QColor(Colors.SUCCESS), 2))
            painter.drawLine(int(points[0]), line_y, int(points[current_index]), line_y)

        label_font = QFont()
        label_font.setPixelSize(9)
        threshold_font = QFont(label_font)
        threshold_font.setPixelSize(8)
        segment = width / max(1, count - 1)

        for index, (x, rank) in enumerate(zip(points, RANKS)):
            if index < current_index:
                fill = QColor(Colors.SUCCESS)
                border = QColor(Colors.SUCCESS)
            elif index == current_index:
                fill = QColor(Colors.ACCENT)
                border = QColor(Colors.ACCENT_HOVER)
            else:
                fill = QColor(Colors.SURFACE_ELEVATED)
                border = QColor(Colors.BORDER_STRONG)
            painter.setPen(QPen(border, 2))
            painter.setBrush(fill)
            painter.drawEllipse(QRectF(x - 6, line_y - 6, 12, 12))

            rect_width = min(100.0, max(54.0, segment - 4))
            text_left = max(
                0.0,
                min(self.width() - rect_width, x - rect_width / 2),
            )
            text_rect = QRectF(text_left, 28, rect_width, 16)
            painter.setFont(label_font)
            painter.setPen(
                QColor(Colors.ACCENT)
                if index == current_index
                else QColor(Colors.TEXT_MUTED)
            )
            metrics = QFontMetrics(label_font)
            label = metrics.elidedText(rank.name, Qt.ElideRight, int(rect_width))
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)
            painter.setFont(threshold_font)
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                QRectF(text_left, 46, rect_width, 14),
                Qt.AlignHCenter | Qt.AlignTop,
                f"Level {rank.minimum_level}",
            )
        painter.end()


class MilestoneTrackWidget(QWidget):
    """Tier nodes and connecting progress for a single milestone track."""

    def __init__(self, track):
        super().__init__()
        self.track = track
        self.state = None
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, state):
        self.state = state
        self.update()

    def _threshold_text(self, value):
        if self.track.unit == "minutes":
            if value % 60 == 0:
                return f"{value // 60}h"
            return format_minutes(value)
        if self.track.unit == "days":
            return f"{value}d"
        if self.track.unit == "levels":
            return f"L{value}"
        return f"{value:,}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        thresholds = self.track.thresholds
        if not thresholds:
            return
        margin = 14
        available = max(1, self.width() - margin * 2)
        points = [
            margin + available * index / max(1, len(thresholds) - 1)
            for index in range(len(thresholds))
        ]
        y = 14
        painter.setPen(QPen(QColor(Colors.BORDER_STRONG), 2))
        painter.drawLine(int(points[0]), y, int(points[-1]), y)

        completed = self.state.completed_tiers if self.state else 0
        value = self.state.current_value if self.state else 0
        if completed > 1:
            painter.setPen(QPen(QColor(Colors.SUCCESS), 3))
            painter.drawLine(int(points[0]), y, int(points[completed - 1]), y)
        if 0 < completed < len(thresholds):
            previous = thresholds[completed - 1]
            target = thresholds[completed]
            ratio = min(1.0, max(0.0, (value - previous) / max(1, target - previous)))
            start = points[completed - 1]
            end = start + (points[completed] - start) * ratio
            painter.setPen(QPen(QColor(Colors.ACCENT), 3))
            painter.drawLine(int(start), y, int(end), y)

        font = QFont()
        font.setPixelSize(8)
        painter.setFont(font)
        for index, (x, threshold) in enumerate(zip(points, thresholds)):
            if index < completed:
                fill = QColor(Colors.SUCCESS)
                border = QColor(Colors.SUCCESS_HOVER)
            elif index == completed and completed < len(thresholds):
                fill = QColor(Colors.SURFACE_ELEVATED)
                border = QColor(Colors.ACCENT)
            else:
                fill = QColor(Colors.SURFACE_ELEVATED)
                border = QColor(Colors.BORDER_STRONG)
            painter.setPen(QPen(border, 2))
            painter.setBrush(fill)
            painter.drawEllipse(QRectF(x - 6, y - 6, 12, 12))
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                QRectF(x - 25, 29, 50, 14),
                Qt.AlignHCenter | Qt.AlignTop,
                self._threshold_text(threshold),
            )
        painter.end()


class MilestoneCard(QFrame):
    """Compact category, tier state, targets and node-based visualization."""

    def __init__(self, track):
        super().__init__()
        self.track = track
        self.setObjectName("MilestoneCard")
        self.setMinimumHeight(154)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM + 2, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.XS)

        heading = QHBoxLayout()
        self.name_label = QLabel(track.name)
        self.name_label.setObjectName("MilestoneName")
        self.tier_label = QLabel("Tier 0 / 4")
        self.tier_label.setObjectName("MilestoneTier")
        heading.addWidget(self.name_label)
        heading.addStretch()
        heading.addWidget(self.tier_label)

        self.description_label = QLabel(track.description)
        self.description_label.setObjectName("MilestoneDescription")
        self.description_label.setWordWrap(True)
        self.track_widget = MilestoneTrackWidget(track)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("MilestoneProgress")
        self.progress_label.setWordWrap(True)
        self.progress_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        layout.addLayout(heading)
        layout.addWidget(self.description_label)
        layout.addWidget(self.track_widget)
        layout.addWidget(self.progress_label)

    def _value_text(self, value):
        if self.track.unit == "minutes":
            return format_minutes(int(value))
        if self.track.unit == "levels":
            return f"Level {int(value)}"
        if self.track.unit == "days":
            return format_day_count(value)
        return f"{int(value):,} {self.track.unit}"

    def set_state(self, state):
        self.track_widget.set_state(state)
        self.tier_label.setText(
            f"Tier {state.completed_tiers} / {len(state.track.thresholds)}"
        )
        if state.next_threshold is None:
            self.progress_label.setText(
                f"{self._value_text(state.current_value)} · all tiers reached"
            )
        else:
            self.progress_label.setText(
                f"{self._value_text(state.current_value)} · next {self._value_text(state.next_threshold)}"
            )


class AchievementCard(QFrame):
    """Compact recognition card shared by featured and catalogue views."""

    def __init__(self, definition, featured=False):
        super().__init__()
        self.definition = definition
        self.featured = featured
        self.setObjectName("AchievementCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(142 if featured else 116)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.XS + 1)

        top = QHBoxLayout()
        self.symbol_label = QLabel(definition.symbol)
        self.symbol_label.setObjectName("AchievementSymbol")
        self.symbol_label.setAlignment(Qt.AlignCenter)
        self.symbol_label.setFixedSize(42, 42)
        self.category_label = QLabel(definition.category)
        self.category_label.setObjectName("AchievementCategory")
        self.category_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.symbol_label)
        top.addStretch()
        top.addWidget(self.category_label)

        self.name_label = QLabel(definition.name)
        self.name_label.setObjectName("AchievementName")
        self.description_label = QLabel(definition.description)
        self.description_label.setObjectName("AchievementDescription")
        self.description_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setObjectName("AchievementStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        layout.addLayout(top)
        layout.addWidget(self.name_label)
        layout.addWidget(self.description_label)
        layout.addStretch()
        layout.addWidget(self.status_label)

    @staticmethod
    def _progress_text(state):
        definition = state.definition
        value = min(state.current_value, definition.threshold)
        if definition.metric == "focus_minutes":
            return f"{format_minutes(int(value))} / {format_minutes(definition.threshold)}"
        if definition.metric == "level":
            return f"Level {int(value)} / {definition.threshold}"
        return f"Progress {int(value):,} / {definition.threshold:,}"

    def set_state(self, state):
        value = "true" if state.unlocked else "false"
        self.setProperty("unlocked", value)
        self.symbol_label.setProperty("unlocked", value)
        self.category_label.setText(
            "Earned" if state.unlocked else state.definition.category
        )
        self.status_label.setText(
            _format_unlock_date(state.unlocked_at)
            if state.unlocked
            else self._progress_text(state)
        )
        _repolish(self)
        _repolish(self.symbol_label)


class AchievementsDialog(QDialog):
    """Secondary collection view containing all persisted achievement states."""

    def __init__(self, states, parent=None):
        super().__init__(parent)
        self.states = tuple(states)
        self.setObjectName("AchievementsDialog")
        self.setWindowTitle("All Achievements")
        self.resize(900, 660)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.XL)
        root.setSpacing(Spacing.MD)
        title_row = QHBoxLayout()
        title = QLabel("All Achievements")
        title.setObjectName("PageTitle")
        earned = sum(1 for state in self.states if state.unlocked)
        summary = QLabel(f"{earned} of {len(self.states)} earned")
        summary.setObjectName("Badge")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(summary)
        subtitle = QLabel(
            "Every recognition is backed by your persisted productivity data."
        )
        subtitle.setObjectName("MutedText")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, Spacing.SM, 0)
        grid.setSpacing(Spacing.SM)
        self.cards = {}
        for index, state in enumerate(self.states):
            card = AchievementCard(state.definition)
            card.set_state(state)
            self.cards[state.definition.identifier] = card
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(content)

        close_button = QPushButton("Close")
        close_button.setObjectName("GhostButton")
        close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(close_button)

        root.addLayout(title_row)
        root.addWidget(subtitle)
        root.addWidget(scroll, 1)
        root.addLayout(footer)


class PlayerProgressPage(QWidget):
    """Information-dense home for verified productivity progression."""

    character_changed = Signal(str)

    def __init__(self, progression_service, character_manager):
        super().__init__()
        self.progression_service = progression_service
        self.character_manager = character_manager
        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)
        self.open_animation = None
        self.compact_layout = None
        self.character_buttons = {}
        self.achievement_cards = {}
        self.achievements_dialog = None
        self.latest_snapshot = None
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
            Spacing.XXL, Spacing.MD, Spacing.XXL, Spacing.XXL
        )
        self.content_layout.setSpacing(Spacing.LG)

        intro = QLabel(
            "Your real work, translated into visible long-term progress."
        )
        intro.setObjectName("MutedText")
        self.content_layout.addWidget(intro)
        self.content_layout.addWidget(self.create_character_card())
        self.content_layout.addWidget(self.create_milestones_section())
        self.content_layout.addWidget(self.create_achievements_section())
        self.character_section = self.create_character_selection_section()
        self.content_layout.addWidget(self.character_section)
        self.content_layout.addStretch()

        self.scroll_area.setWidget(content)
        root_layout.addWidget(self.scroll_area)

    def _section(self, title, description=""):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(
            Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG
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

    def create_character_card(self):
        self.hero_card = QFrame()
        self.hero_card.setObjectName("ProgressHeroCard")
        self.hero_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hero_card.setMinimumHeight(308)
        layout = QHBoxLayout(self.hero_card)
        layout.setContentsMargins(0, 0, Spacing.LG, 0)
        layout.setSpacing(Spacing.LG)

        visual = QFrame()
        visual.setObjectName("CharacterVisualPane")
        visual.setFixedWidth(238)
        visual_layout = QVBoxLayout(visual)
        visual_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.MD)
        visual_layout.setSpacing(2)
        self.character_sprite = CharacterSprite()
        self.character_sprite.setMinimumHeight(214)
        self.character_name_label = QLabel()
        self.character_name_label.setObjectName("CharacterName")
        self.character_name_label.setAlignment(Qt.AlignCenter)
        self.evolution_label = QLabel()
        self.evolution_label.setObjectName("CharacterStage")
        self.evolution_label.setAlignment(Qt.AlignCenter)
        self.change_character_button = self.button_factory.secondary(
            "Change Character", "fa5s.user-edit"
        )
        self.change_character_button.setObjectName("CharacterChangeButton")
        self.change_character_button.clicked.connect(self.scroll_to_characters)
        visual_layout.addWidget(self.character_sprite, 1)
        visual_layout.addWidget(self.character_name_label)
        visual_layout.addWidget(self.evolution_label)
        visual_layout.addWidget(self.change_character_button, alignment=Qt.AlignCenter)

        info = QVBoxLayout()
        info.setContentsMargins(0, Spacing.MD, 0, Spacing.MD)
        info.setSpacing(Spacing.SM)
        identity = QHBoxLayout()
        level_box = QVBoxLayout()
        level_box.setSpacing(0)
        level_caption = QLabel("LEVEL")
        level_caption.setObjectName("ProgressEyebrow")
        self.level_title = QLabel("Level 1")
        self.level_title.setObjectName("ProgressLevel")
        level_box.addWidget(level_caption)
        level_box.addWidget(self.level_title)
        rank_box = QVBoxLayout()
        rank_box.setSpacing(0)
        rank_caption = QLabel("CURRENT RANK")
        rank_caption.setObjectName("ProgressEyebrow")
        self.rank_label = QLabel("Starting Out")
        self.rank_label.setObjectName("PlayerRank")
        rank_box.addWidget(rank_caption)
        rank_box.addWidget(self.rank_label)
        identity.addLayout(level_box)
        identity.addSpacing(Spacing.XL)
        identity.addLayout(rank_box, 1)

        xp_labels = QHBoxLayout()
        self.total_xp_label = QLabel("0 total XP")
        self.total_xp_label.setObjectName("PlayerXpStrong")
        self.next_level_label = QLabel("100 XP to Level 2")
        self.next_level_label.setObjectName("MutedText")
        self.next_level_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        xp_labels.addWidget(self.total_xp_label)
        xp_labels.addStretch()
        xp_labels.addWidget(self.next_level_label)
        self.level_bar = QProgressBar()
        self.level_bar.setObjectName("XpBar")
        self.level_bar.setTextVisible(False)
        self.level_bar.setRange(0, XP_PER_LEVEL)

        stats = QHBoxLayout()
        stats.setSpacing(Spacing.XS + 2)
        self.stat_cards = {
            "current_streak": ProgressStatCard("Current Streak", "amber", "amber"),
            "best_streak": ProgressStatCard("Best Streak", "blue", "blue"),
            "focus_time": ProgressStatCard("Focus Time", "blue", "blue"),
            "completed_activities": ProgressStatCard("Completed", "green", "green"),
            "completion": ProgressStatCard("Goal Success", "green", "green"),
        }
        for card in self.stat_cards.values():
            stats.addWidget(card, 1)

        path_header = QLabel("Your progression")
        path_header.setObjectName("ProgressEyebrow")
        self.rank_path = RankProgressWidget()

        info.addLayout(identity)
        info.addLayout(xp_labels)
        info.addWidget(self.level_bar)
        info.addLayout(stats)
        info.addWidget(path_header)
        info.addWidget(self.rank_path)

        layout.addWidget(visual)
        layout.addLayout(info, 1)
        return self.hero_card

    def create_milestones_section(self):
        section, layout, _heading = self._section(
            "Milestones",
            "Broader tracks that show your long-term growth and next meaningful target.",
        )
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(Spacing.SM)
        grid.setVerticalSpacing(Spacing.SM)
        self.milestones_grid = grid
        self.milestone_rows = {}
        for index, track in enumerate(MILESTONE_TRACKS):
            card = MilestoneCard(track)
            self.milestone_rows[track.identifier] = card
            grid.addWidget(card, 0, index)
            grid.setColumnStretch(index, 1)
        layout.addLayout(grid)
        return section

    def create_achievements_section(self):
        section, layout, heading = self._section(
            "Achievements",
            "Recent recognitions and the accomplishments closest to completion.",
        )
        self.achievement_summary_label = QLabel()
        self.achievement_summary_label.setObjectName("Badge")
        self.view_all_achievements_button = self.button_factory.secondary(
            "View All", "fa5s.th-large"
        )
        self.view_all_achievements_button.setObjectName("SectionLinkButton")
        self.view_all_achievements_button.clicked.connect(self.show_all_achievements)
        heading.addWidget(self.achievement_summary_label)
        heading.addWidget(self.view_all_achievements_button)

        self.featured_achievements_grid = QGridLayout()
        self.featured_achievements_grid.setContentsMargins(0, 0, 0, 0)
        self.featured_achievements_grid.setSpacing(Spacing.SM)
        for column in range(FEATURED_ACHIEVEMENT_LIMIT):
            self.featured_achievements_grid.setColumnStretch(column, 1)
        layout.addLayout(self.featured_achievements_grid)
        return section

    def create_character_selection_section(self):
        section, layout, _heading = self._section(
            "Character Library",
            "Choose an original 2D character to represent your progress. Every character is available.",
        )
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.SM)
        self.character_button_group = QButtonGroup(self)
        self.character_button_group.setExclusive(True)

        for index, character in enumerate(CHARACTERS):
            button = QToolButton()
            button.setText(character.name)
            button.setObjectName("CharacterChoice")
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setMinimumHeight(132)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            button.setIconSize(character_pixmap(character, "stage_1", 76).size())
            button.clicked.connect(
                lambda _checked=False, identifier=character.identifier: self.select_character(identifier)
            )
            self.character_button_group.addButton(button)
            self.character_buttons[character.identifier] = button
            grid.addWidget(button, 0, index)
        for column in range(len(CHARACTERS)):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        return section

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _apply_responsive_layout(self, width):
        compact = width < 980
        if compact == self.compact_layout:
            return
        self.compact_layout = compact

        if hasattr(self, "milestones_grid"):
            while self.milestones_grid.count():
                self.milestones_grid.takeAt(0)
            columns = 3 if compact else len(MILESTONE_TRACKS)
            for column in range(len(MILESTONE_TRACKS)):
                self.milestones_grid.setColumnStretch(column, 0)
            for index, track in enumerate(MILESTONE_TRACKS):
                self.milestones_grid.addWidget(
                    self.milestone_rows[track.identifier],
                    index // columns,
                    index % columns,
                )
            for column in range(columns):
                self.milestones_grid.setColumnStretch(column, 1)

        if self.latest_snapshot is not None and hasattr(
            self,
            "featured_achievements_grid",
        ):
            self._refresh_featured_achievements(
                self.latest_snapshot.achievements
            )

    def _clear_featured_cards(self):
        while self.featured_achievements_grid.count():
            item = self.featured_achievements_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.achievement_cards = {}

    def _refresh_featured_achievements(self, states):
        self._clear_featured_cards()
        selected = featured_achievement_states(states)
        self.featured_achievement_ids = tuple(
            state.definition.identifier for state in selected
        )
        columns = 2 if self.compact_layout else FEATURED_ACHIEVEMENT_LIMIT
        for column in range(FEATURED_ACHIEVEMENT_LIMIT):
            self.featured_achievements_grid.setColumnStretch(column, 0)
        for column in range(columns):
            self.featured_achievements_grid.setColumnStretch(column, 1)
        for index, state in enumerate(selected):
            card = AchievementCard(state.definition, featured=True)
            card.set_state(state)
            self.achievement_cards[state.definition.identifier] = card
            self.featured_achievements_grid.addWidget(
                card,
                index // columns,
                index % columns,
            )

    def show_all_achievements(self):
        snapshot = self.progression_service.snapshot()
        dialog = AchievementsDialog(snapshot.achievements, self)
        dialog.finished.connect(lambda _result: setattr(self, "achievements_dialog", None))
        self.achievements_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def scroll_to_characters(self):
        self.scroll_area.ensureWidgetVisible(self.character_section, 0, Spacing.MD)

    def select_character(self, character_id):
        if self.character_manager.select(character_id):
            self.character_changed.emit(character_id)
        self.refresh()

    def refresh_character_icons(self, stage_identifier="stage_1"):
        for character in CHARACTERS:
            button = self.character_buttons[character.identifier]
            pixmap = character_pixmap(character, stage_identifier, 76)
            button.setIcon(QIcon(pixmap))
            button.setIconSize(pixmap.size())

    def refresh(self):
        """Render one real persisted progression snapshot."""
        snapshot = self.progression_service.snapshot()
        self.latest_snapshot = snapshot
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
        self.rank_label.setText(snapshot.rank.name)
        self.level_title.setText(f"Level {metrics.level}")
        self.total_xp_label.setText(
            f"{level_xp} / {XP_PER_LEVEL} XP  ·  {metrics.total_xp:,} total"
        )
        self.next_level_label.setText(
            f"{xp_remaining} XP to Level {metrics.level + 1}"
        )
        self.level_bar.setValue(level_xp)
        self.rank_path.set_level(metrics.level)

        self.stat_cards["current_streak"].set_value(
            format_day_count(metrics.current_streak)
        )
        self.stat_cards["best_streak"].set_value(
            format_day_count(metrics.best_streak)
        )
        self.stat_cards["focus_time"].set_value(
            format_minutes(metrics.focus_minutes)
        )
        self.stat_cards["completed_activities"].set_value(
            f"{metrics.completed_activities:,}"
        )
        self.stat_cards["completion"].set_value(
            f"{metrics.goal_completion_rate:g}%"
        )

        for state in snapshot.milestones:
            self.milestone_rows[state.track.identifier].set_state(state)

        unlocked_count = sum(1 for state in snapshot.achievements if state.unlocked)
        self.achievement_summary_label.setText(
            f"{unlocked_count} of {len(snapshot.achievements)} earned"
        )
        self._refresh_featured_achievements(snapshot.achievements)

        selected_id = snapshot.character.identifier
        for identifier, button in self.character_buttons.items():
            button.setChecked(identifier == selected_id)
        self.refresh_character_icons(snapshot.evolution_stage.identifier)

    def animate_open(self):
        """Preserve the existing subtle, non-blocking 420 ms entrance."""
        if self.open_animation is not None:
            self.open_animation.stop()
        effect = self.hero_card.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.hero_card)
            self.hero_card.setGraphicsEffect(effect)
        effect.setOpacity(0.65)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(420)
        animation.setStartValue(0.65)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self.open_animation = animation
        animation.start()
