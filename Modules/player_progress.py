"""Player Progress Dashboard.

Comprehensive progression identity, macro milestone tracking, and achievement library.
Consumes authoritative ProgressionService, CharacterManager, and AchievementManager.
"""

import math

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal, QVariantAnimation
from PySide6.QtWidgets import (
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

from Dialogs.achievement_library_dialog import AchievementLibraryDialog
from Dialogs.character_selector_dialog import CharacterSelectorDialog
from Modules.achievement_manager import ACHIEVEMENT_DEFINITIONS, MILESTONE_CATALOG, AchievementManager
from Modules.character_asset_manager import CharacterAssetManager
from Modules.character_manager import CharacterManager, get_evolution_stage
from Modules.insights_service import format_day_count
from Modules.progression_service import ProgressionService
from UI.theme.design_system import Colors, Radius, Spacing, Typography
from UI.theme.motion_utils import is_reduced_motion_enabled

XP_PER_LEVEL = 100


class StageEvolutionIndicatorWidget(QFrame):
    """Compact 4-stage evolution journey indicator."""

    STAGE_TITLES = {
        1: "Initiated",
        2: "Established",
        3: "Ascended",
        4: "Sovereign",
    }

    def __init__(self, current_stage=1):
        super().__init__()
        self.setObjectName("EvolutionIndicator")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._current_stage = max(1, min(int(current_stage), 4))
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, Spacing.XS, 0, Spacing.XS)
        self.main_layout.setSpacing(Spacing.SM)

        self.node_widgets = {}
        self.build_ui()

    def build_ui(self):
        for stage_idx in range(1, 5):
            node_layout = QHBoxLayout()
            node_layout.setSpacing(Spacing.XS)

            dot = QLabel()
            dot.setFixedSize(14, 14)
            dot.setAlignment(Qt.AlignCenter)

            label = QLabel(f"S{stage_idx} {self.STAGE_TITLES[stage_idx]}")

            node_layout.addWidget(dot)
            node_layout.addWidget(label)
            self.main_layout.addLayout(node_layout)

            line = None
            if stage_idx < 4:
                line = QLabel("───")
                self.main_layout.addWidget(line)

            self.node_widgets[stage_idx] = {
                "dot": dot,
                "label": label,
                "line": line,
            }

        self.main_layout.addStretch()
        self.update_stage_styles()

    def update_stage_styles(self):
        for stage_idx in range(1, 5):
            node = self.node_widgets[stage_idx]
            dot = node["dot"]
            label = node["label"]
            line = node["line"]

            if stage_idx < self._current_stage:
                dot.setText("●")
                dot.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: bold;")
                label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 12px; font-weight: 600;")
            elif stage_idx == self._current_stage:
                dot.setText("◉")
                dot.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 13px; font-weight: bold;")
                label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 750;")
            else:
                dot.setText("○")
                dot.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
                label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 500;")

            if line is not None:
                line.setStyleSheet(f"color: {Colors.BORDER_STRONG if stage_idx < self._current_stage else Colors.BORDER}; font-size: 10px;")

    def set_stage(self, current_stage):
        new_stage = max(1, min(int(current_stage), 4))
        if new_stage != self._current_stage:
            self._current_stage = new_stage
            self.update_stage_styles()


class MilestoneCardWidget(QFrame):
    """Card representing one of the four macro productivity milestone categories."""

    def __init__(self, title, icon_str, current_val, milestone_id, tint=None):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.MD + 2)
        layout.setSpacing(Spacing.SM)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(Spacing.SM)

        icon_label = QLabel(icon_str)
        icon_label.setObjectName("Badge")

        title_label = QLabel(title)
        title_label.setObjectName("InsightMetricTitle")

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.tier_badge = QLabel("Tier 1")
        self.tier_badge.setObjectName("Badge")
        header_layout.addWidget(self.tier_badge)

        layout.addLayout(header_layout)

        # Value row
        self.val_label = QLabel("—")
        self.val_label.setObjectName("InsightMetricValue")
        layout.addWidget(self.val_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("XpBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        # Target note
        self.note_label = QLabel()
        self.note_label.setObjectName("InsightMetricNote")
        layout.addWidget(self.note_label)

        self.update_data(current_val, milestone_id)

    def enterEvent(self, event):
        super().enterEvent(event)
        if not is_reduced_motion_enabled():
            self.setProperty("hovered", "true")
            self.setStyle(self.style())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not is_reduced_motion_enabled():
            self.setProperty("hovered", "false")
            self.setStyle(self.style())

    def update_data(self, current_val, milestone_id):
        cat_info = MILESTONE_CATALOG.get(milestone_id)
        if not cat_info:
            return

        unit = cat_info["unit"]
        if unit == "hours":
            val_display = f"{current_val // 60}h {current_val % 60}m" if current_val >= 60 else f"{current_val}m"
        else:
            val_display = f"{current_val:,}"

        self.val_label.setText(val_display)

        tiers = cat_info["tiers"]
        reached_tier = 0
        next_threshold = tiers[-1]["threshold"]
        next_label = tiers[-1]["label"]

        for t in tiers:
            if current_val >= t["threshold"]:
                reached_tier = t["tier"]
            else:
                next_threshold = t["threshold"]
                next_label = t["label"]
                break

        if reached_tier >= len(tiers):
            self.tier_badge.setText("Tier 5 (Max)")
            self.tier_badge.setObjectName("CompletedBadge")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.note_label.setText(f"Mastery Achieved ({tiers[-1]['label']})")
        else:
            self.tier_badge.setText(f"Tier {reached_tier} of {len(tiers)}")
            self.tier_badge.setObjectName("Badge")
            prev_threshold = tiers[reached_tier - 1]["threshold"] if reached_tier > 0 else 0
            span = max(1, next_threshold - prev_threshold)
            prog_into = max(0, current_val - prev_threshold)
            self.progress_bar.setRange(0, span)
            self.progress_bar.setValue(min(prog_into, span))

            rem = next_threshold - current_val
            if unit == "hours":
                rem_str = f"{rem // 60}h" if rem >= 60 else f"{rem}m"
            else:
                rem_str = f"{rem:,}"
            self.note_label.setText(f"Next: {next_label} ({rem_str} remaining)")

        self.tier_badge.setStyle(self.tier_badge.style())


class PlayerProgressPage(QWidget):
    """Complete progression dashboard experience."""

    NEUTRAL_Y = 8
    IDLE_DURATION_MS = 3500
    TRANSITION_DURATION_MS = 300

    def __init__(self, xp_manager, streak_manager, progression_service=None, character_manager=None):
        super().__init__()
        self.xp_manager = xp_manager
        self.streak_manager = streak_manager
        self.database = xp_manager.database

        self.character_manager = character_manager or CharacterManager(self.database)

        if progression_service is None:
            ach_mgr = AchievementManager(self.database, self.streak_manager, self.xp_manager)
            self.progression_service = ProgressionService(
                self.database,
                self.xp_manager,
                self.streak_manager,
                ach_mgr,
                self.character_manager,
            )
        else:
            self.progression_service = progression_service

        self.asset_mgr = CharacterAssetManager()

        # Motion & Presentation Lifecycle Controllers
        self._idle_anim = None
        self._switch_anim = None
        self._xp_anim = None
        self._opacity_effect = None
        self._current_displayed_char_id = None
        self._current_displayed_stage = None
        self._pixmap_swapped = False

        # Phase 5B Progression Feedback State Tracking
        self._last_xp_into = None
        self._last_xp_for = None
        self._last_level = None
        self._last_stage = None
        self._known_unlocked_ids = None

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
        layout.setSpacing(Spacing.XL)

        # Page Header
        layout.addLayout(self.create_header())

        # Hero / Identity Card
        layout.addWidget(self.create_hero_card())

        # Macro Milestones Section
        layout.addWidget(self.create_milestones_section())

        # Recent Achievements Section
        layout.addWidget(self.create_achievements_section())

        layout.addStretch()
        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def create_header(self):
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        self.title_label = QLabel("Player Progress")
        self.title_label.setObjectName("PageTitle")

        self.subtitle_label = QLabel("Your journey, milestones, and evolution.")
        self.subtitle_label.setObjectName("MutedText")

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)
        return header_layout

    def create_hero_card(self):
        card = QFrame()
        card.setObjectName("HeroCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.XXL)

        # LEFT: Large Character Portrait Frame (200x200 sprite rendering area)
        portrait_frame = QFrame()
        portrait_frame.setObjectName("CharacterPortraitFrame")
        portrait_frame.setFixedSize(216, 216)

        self.avatar_label = QLabel(portrait_frame)
        self.avatar_label.setFixedSize(200, 200)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.move(8, self.NEUTRAL_Y)

        layout.addWidget(portrait_frame, alignment=Qt.AlignTop | Qt.AlignLeft)

        # RIGHT: Character Progression & Identity Details
        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(Spacing.MD)

        # Row 1: Character Name & Stage Badge & Switch Character Button
        title_row = QHBoxLayout()
        title_row.setSpacing(Spacing.MD)

        self.char_name_label = QLabel("The Architect")
        self.char_name_label.setObjectName("CharacterNameHeading")

        self.stage_badge = QLabel("Stage 1 — Initiated")
        self.stage_badge.setObjectName("CompletedBadge")

        title_row.addWidget(self.char_name_label)
        title_row.addWidget(self.stage_badge)
        title_row.addStretch()

        self.switch_char_btn = QPushButton("Switch Character")
        self.switch_char_btn.setObjectName("GhostButton")
        self.switch_char_btn.setCursor(Qt.PointingHandCursor)
        self.switch_char_btn.clicked.connect(self.open_character_selector)
        title_row.addWidget(self.switch_char_btn)

        detail_layout.addLayout(title_row)

        # Row 2: Character Specialization Identity
        self.char_identity_label = QLabel("Focus & Planning Mastery")
        self.char_identity_label.setObjectName("MutedText")
        self.char_identity_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        detail_layout.addWidget(self.char_identity_label)

        # Row 3: Compact 4-Stage Evolution Journey Indicator
        self.evolution_indicator = StageEvolutionIndicatorWidget(current_stage=1)
        detail_layout.addWidget(self.evolution_indicator)

        # Row 4: Prominent Level & Total XP Callout
        level_xp_row = QHBoxLayout()
        level_xp_row.setSpacing(Spacing.LG)
        level_xp_row.setAlignment(Qt.AlignBottom)

        self.level_title = QLabel("Level 1")
        self.level_title.setObjectName("PlayerLevelHeading")
        self.level_title.setStyleSheet("font-size: 30px; font-weight: 850;")

        self.total_xp_label = QLabel("0 XP earned in total")
        self.total_xp_label.setObjectName("MutedText")
        self.total_xp_label.setStyleSheet("font-size: 13px; font-weight: 500;")

        level_xp_row.addWidget(self.level_title)
        level_xp_row.addWidget(self.total_xp_label)
        level_xp_row.addStretch()
        detail_layout.addLayout(level_xp_row)

        # Row 4: High-Impact Progress Bar
        self.level_bar = QProgressBar()
        self.level_bar.setObjectName("XpBarHero")
        self.level_bar.setTextVisible(False)
        self.level_bar.setRange(0, 100)
        self.level_bar.setFixedHeight(14)
        detail_layout.addWidget(self.level_bar)

        # Row 5: Precise XP Progress Text Readout
        self.next_level_label = QLabel()
        self.next_level_label.setObjectName("XpProgressText")
        detail_layout.addWidget(self.next_level_label)

        layout.addLayout(detail_layout, 1)
        return card

    def create_milestones_section(self):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(section)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.LG)

        title = QLabel("Macro Milestones")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.MD)

        self.milestone_cards = {
            "focus_duration": MilestoneCardWidget("Focus Duration", "⏱", 0, "focus_duration", tint="blue"),
            "completed_activities": MilestoneCardWidget("Tasks Done", "✅", 0, "completed_activities", tint="purple"),
            "daily_goal_days": MilestoneCardWidget("Goal Days", "🎯", 0, "daily_goal_days", tint="green"),
            "longest_streak": MilestoneCardWidget("Longest Streak", "🔥", 0, "longest_streak", tint="amber"),
        }

        self.stat_cards = {
            "current_streak": self.milestone_cards["longest_streak"],
            "best_streak": self.milestone_cards["focus_duration"],
            "goal_days": self.milestone_cards["daily_goal_days"],
            "completion": self.milestone_cards["completed_activities"],
        }

        for column, (key, card) in enumerate(self.milestone_cards.items()):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)

        layout.addLayout(grid)
        return section

    def create_achievements_section(self):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(section)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        # Header Row
        header_row = QHBoxLayout()

        title = QLabel("Recent Achievements")
        title.setObjectName("SectionTitle")

        self.view_all_ach_btn = QPushButton("View All Achievements")
        self.view_all_ach_btn.setObjectName("GhostButton")
        self.view_all_ach_btn.setCursor(Qt.PointingHandCursor)
        self.view_all_ach_btn.clicked.connect(self.open_achievement_library)

        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.view_all_ach_btn)
        layout.addLayout(header_row)

        # Recent Items Container
        self.achievements_container = QVBoxLayout()
        self.achievements_container.setSpacing(Spacing.SM)
        layout.addLayout(self.achievements_container)

        return section

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        if not is_reduced_motion_enabled():
            self.start_idle_animation()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.stop_idle_animation()
        if self._switch_anim is not None and self._switch_anim.state() == QVariantAnimation.Running:
            self._switch_anim.stop()

    def start_idle_animation(self):
        """Start gentle vertical idle breathing animation if allowed."""
        if is_reduced_motion_enabled():
            self.stop_idle_animation()
            return

        if not self.isVisible():
            return

        if self._idle_anim is not None and self._idle_anim.state() == QVariantAnimation.Running:
            return

        if self._idle_anim is None:
            self._idle_anim = QVariantAnimation(self)
            self._idle_anim.setStartValue(0.0)
            self._idle_anim.setEndValue(1.0)
            self._idle_anim.setDuration(self.IDLE_DURATION_MS)
            self._idle_anim.setLoopCount(-1)
            self._idle_anim.valueChanged.connect(self._on_idle_anim_frame)

        self._idle_anim.start()

    def stop_idle_animation(self):
        """Stop idle animation safely and restore neutral portrait position."""
        if self._idle_anim is not None:
            self._idle_anim.stop()
        if hasattr(self, "avatar_label") and self.avatar_label is not None:
            self.avatar_label.move(8, self.NEUTRAL_Y)

    def _on_idle_anim_frame(self, progress):
        """Continuous sinusoidal y-displacement calculation: ±3px travel over 3500ms cycle."""
        if is_reduced_motion_enabled() or not self.isVisible():
            self.stop_idle_animation()
            return
        progress_float = float(progress)
        y_offset = int(round(-3.0 * math.sin(2.0 * math.pi * progress_float)))
        self.avatar_label.move(8, self.NEUTRAL_Y + y_offset)

    def _trigger_character_switch_transition(self, target_char_id, target_stage):
        """Perform smooth ~300ms fade out -> swap sprite -> fade in transition."""
        if is_reduced_motion_enabled():
            pixmap = self.asset_mgr.get_character_pixmap(target_char_id, stage=target_stage, width=200, height=200)
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.move(8, self.NEUTRAL_Y)
            self._current_displayed_char_id = target_char_id
            self._current_displayed_stage = target_stage
            return

        self.stop_idle_animation()

        if self._switch_anim is not None and self._switch_anim.state() == QVariantAnimation.Running:
            self._switch_anim.stop()

        if self._opacity_effect is None or self.avatar_label.graphicsEffect() != self._opacity_effect:
            self._opacity_effect = QGraphicsOpacityEffect(self.avatar_label)
            self.avatar_label.setGraphicsEffect(self._opacity_effect)

        self._pixmap_swapped = False
        self._current_displayed_char_id = target_char_id
        self._current_displayed_stage = target_stage

        def on_switch_frame(val):
            v = float(val)
            if v <= 0.5:
                # 0-150ms: opacity 1.0 -> 0.0
                opacity = max(0.0, 1.0 - (v / 0.5))
                self._opacity_effect.setOpacity(opacity)
            else:
                # Midpoint swap: update sprite to authoritative character selection
                if not self._pixmap_swapped:
                    curr_summary = self.progression_service.get_progression_summary()
                    curr_char = curr_summary["character"]
                    curr_stage = curr_summary["evolution_info"]["stage"]
                    pixmap = self.asset_mgr.get_character_pixmap(curr_char["id"], stage=curr_stage, width=200, height=200)
                    self.avatar_label.setPixmap(pixmap)
                    self._current_displayed_char_id = curr_char["id"]
                    self._current_displayed_stage = curr_stage
                    self._pixmap_swapped = True

                # 150-300ms: opacity 0.0 -> 1.0
                opacity = min(1.0, (v - 0.5) / 0.5)
                self._opacity_effect.setOpacity(opacity)

        def on_switch_finished():
            # Final authoritative check & cleanup
            curr_summary = self.progression_service.get_progression_summary()
            curr_char = curr_summary["character"]
            curr_stage = curr_summary["evolution_info"]["stage"]
            pixmap = self.asset_mgr.get_character_pixmap(curr_char["id"], stage=curr_stage, width=200, height=200)
            self.avatar_label.setPixmap(pixmap)
            self._current_displayed_char_id = curr_char["id"]
            self._current_displayed_stage = curr_stage

            self._opacity_effect.setOpacity(1.0)
            if self.isVisible() and not is_reduced_motion_enabled():
                self.start_idle_animation()

        self._switch_anim = QVariantAnimation(self)
        self._switch_anim.setStartValue(0.0)
        self._switch_anim.setEndValue(1.0)
        self._switch_anim.setDuration(self.TRANSITION_DURATION_MS)
        self._switch_anim.valueChanged.connect(on_switch_frame)
        self._switch_anim.finished.connect(on_switch_finished)
        self._switch_anim.start()

    def _animate_xp_progress(self, old_xp_into, target_xp_into, old_level, new_level, xp_for):
        """Smoothly animate level_bar progress towards authoritative xp_into value (~400ms, OutCubic)."""
        if is_reduced_motion_enabled():
            self.level_bar.setRange(0, xp_for)
            self.level_bar.setValue(target_xp_into)
            return

        if self._xp_anim is not None and self._xp_anim.state() == QPropertyAnimation.Running:
            self._xp_anim.stop()

        self.level_bar.setRange(0, xp_for)
        start_val = self.level_bar.value()

        if new_level > old_level:
            self._xp_anim = QPropertyAnimation(self.level_bar, b"value", self)
            self._xp_anim.setDuration(220)
            self._xp_anim.setStartValue(start_val)
            self._xp_anim.setEndValue(xp_for)
            self._xp_anim.setEasingCurve(QEasingCurve.OutCubic)

            def on_first_phase_done():
                self.level_bar.setValue(0)
                self._xp_anim = QPropertyAnimation(self.level_bar, b"value", self)
                self._xp_anim.setDuration(220)
                self._xp_anim.setStartValue(0)
                self._xp_anim.setEndValue(target_xp_into)
                self._xp_anim.setEasingCurve(QEasingCurve.OutCubic)

                def on_second_phase_done():
                    self.level_bar.setValue(target_xp_into)

                self._xp_anim.finished.connect(on_second_phase_done)
                self._xp_anim.start()

            self._xp_anim.finished.connect(on_first_phase_done)
            self._xp_anim.start()
        else:
            self._xp_anim = QPropertyAnimation(self.level_bar, b"value", self)
            self._xp_anim.setDuration(400)
            self._xp_anim.setStartValue(start_val)
            self._xp_anim.setEndValue(target_xp_into)
            self._xp_anim.setEasingCurve(QEasingCurve.OutCubic)

            def on_xp_anim_done():
                self.level_bar.setValue(target_xp_into)

            self._xp_anim.finished.connect(on_xp_anim_done)
            self._xp_anim.start()

    def _handle_level_up_feedback(self, new_level):
        """Provide a restrained presentation moment for genuine level increases."""
        from UI.components.toast_notification import ToastNotification
        ToastNotification.show_toast(
            self,
            f"LEVEL {new_level} UNLOCKED!",
            f"Outstanding focus! You reached Level {new_level}.",
            icon_str="🚀",
        )

    def refresh(self):
        """Re-read authoritative progression services and refresh all UI sections with presentation feedback."""
        summary = self.progression_service.get_progression_summary()

        total_xp = summary["total_xp"]
        level = summary["level"]
        xp_into = summary["xp_into_level"]
        xp_for = summary["xp_for_level"]
        xp_rem = summary["xp_remaining"]
        evolution = summary["evolution_info"]
        char = summary["character"]

        target_char_id = char["id"]
        target_stage = evolution["stage"]

        curr_unlocked_ids = set(self.progression_service.achievement_manager.get_unlocked_ids())

        # Determine deltas if previous state exists
        is_initial_load = self._last_level is None
        stage_evolved = not is_initial_load and (target_stage > self._last_stage)
        level_up = not is_initial_load and (level > self._last_level)
        xp_changed = not is_initial_load and (xp_into != self._last_xp_into or level != self._last_level)
        newly_unlocked_ids = set() if is_initial_load or self._known_unlocked_ids is None else (curr_unlocked_ids - self._known_unlocked_ids)

        # Update Hero Card Text
        self.char_name_label.setText(char["name"])
        self.char_identity_label.setText(char["title"])
        self.stage_badge.setText(f"Stage {evolution['stage']} — {evolution['name']}")
        self.evolution_indicator.set_stage(target_stage)
        self.level_title.setText(f"Level {level}")
        self.total_xp_label.setText(f"{total_xp:,} XP earned in total")
        self.next_level_label.setText(
            f"{xp_into} / {xp_for} XP  •  {xp_rem} XP to Level {level + 1}"
        )

        # Update Macro Milestones
        focus_mins = self.database.get_total_focus_minutes()
        tasks_done = self.database.get_total_completed_activities()
        goal_days = summary["total_goal_days"]
        longest_streak = summary["longest_streak"]

        self.milestone_cards["focus_duration"].update_data(focus_mins, "focus_duration")
        self.milestone_cards["completed_activities"].update_data(tasks_done, "completed_activities")
        self.milestone_cards["daily_goal_days"].update_data(goal_days, "daily_goal_days")
        self.milestone_cards["longest_streak"].update_data(longest_streak, "longest_streak")

        # Update Recent Achievements (with smooth fade-in for newly unlocked items)
        self.refresh_recent_achievements(newly_unlocked_ids=newly_unlocked_ids)

        # Handle Character Avatar Portrait Motion & Switch Transition
        if is_reduced_motion_enabled():
            self.stop_idle_animation()
            if self._switch_anim is not None and self._switch_anim.state() == QVariantAnimation.Running:
                self._switch_anim.stop()
            if self._xp_anim is not None and self._xp_anim.state() == QPropertyAnimation.Running:
                self._xp_anim.stop()
            if self._opacity_effect is not None:
                self._opacity_effect.setOpacity(1.0)

            self.level_bar.setRange(0, xp_for)
            self.level_bar.setValue(xp_into)

            pixmap = self.asset_mgr.get_character_pixmap(target_char_id, stage=target_stage, width=200, height=200)
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.move(8, self.NEUTRAL_Y)
            self._current_displayed_char_id = target_char_id
            self._current_displayed_stage = target_stage
        else:
            if is_initial_load:
                self.level_bar.setRange(0, xp_for)
                self.level_bar.setValue(xp_into)

                pixmap = self.asset_mgr.get_character_pixmap(target_char_id, stage=target_stage, width=200, height=200)
                self.avatar_label.setPixmap(pixmap)
                self.avatar_label.move(8, self.NEUTRAL_Y)
                self._current_displayed_char_id = target_char_id
                self._current_displayed_stage = target_stage
                if self.isVisible():
                    self.start_idle_animation()
            else:
                # Coordinate events according to priority hierarchy:
                # 1. Evolution Stage  2. Level Up  3. Achievement Unlock  4. XP Progress
                if stage_evolved or self._current_displayed_char_id != target_char_id or self._current_displayed_stage != target_stage:
                    self._trigger_character_switch_transition(target_char_id, target_stage)

                if level_up:
                    self._handle_level_up_feedback(level)

                if xp_changed:
                    self._animate_xp_progress(self._last_xp_into or 0, xp_into, self._last_level or level, level, xp_for)
                else:
                    self.level_bar.setRange(0, xp_for)
                    self.level_bar.setValue(xp_into)

                if self.isVisible() and (self._idle_anim is None or self._idle_anim.state() != QVariantAnimation.Running):
                    self.start_idle_animation()

        # Update tracked state to current authoritative values
        self._last_xp_into = xp_into
        self._last_xp_for = xp_for
        self._last_level = level
        self._last_stage = target_stage
        self._known_unlocked_ids = curr_unlocked_ids

    def refresh_recent_achievements(self, newly_unlocked_ids=None):
        """Render recent unlocked achievements with presentation feedback for new unlocks."""
        if newly_unlocked_ids is None:
            newly_unlocked_ids = set()

        # Clear existing widgets
        while self.achievements_container.count():
            item = self.achievements_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        unlocked_rows = self.database.get_unlocked_achievements()
        if not unlocked_rows:
            empty_card = QFrame()
            empty_card.setObjectName("InsightItem")
            el = QHBoxLayout(empty_card)
            el.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)

            note = QLabel("No achievements unlocked yet. Complete daily goals, focus sessions, and tasks to earn badges.")
            note.setObjectName("MutedText")
            el.addWidget(note)
            self.achievements_container.addWidget(empty_card)
            return

        # Render up to 3 recent unlocked achievements
        for row in reversed(unlocked_rows[-3:]):
            aid = row["achievement_id"] if isinstance(row, dict) else row[0]
            unlocked_at = row["unlocked_at"] if isinstance(row, dict) else row[1]
            ach_info = ACHIEVEMENT_DEFINITIONS.get(aid)
            if not ach_info:
                continue

            card = QFrame()
            card.setObjectName("InsightItem")
            card.setProperty("selected", "true")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
            cl.setSpacing(Spacing.MD)

            icon = QLabel(ach_info["icon"])
            icon.setObjectName("LevelBadge")
            icon.setFixedSize(48, 48)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("font-size: 22px;")

            txt_l = QVBoxLayout()
            txt_l.setSpacing(2)

            name_lbl = QLabel(ach_info["name"])
            name_lbl.setObjectName("Greeting")
            name_lbl.setStyleSheet("font-size: 15px; font-weight: 750;")

            desc_lbl = QLabel(ach_info["description"])
            desc_lbl.setObjectName("MutedText")

            txt_l.addWidget(name_lbl)
            txt_l.addWidget(desc_lbl)

            date_str = unlocked_at.split("T")[0] if "T" in str(unlocked_at) else str(unlocked_at)
            date_lbl = QLabel(f"Unlocked: {date_str}" if date_str else "Unlocked")
            date_lbl.setObjectName("CompletedBadge")

            cl.addWidget(icon)
            cl.addLayout(txt_l, 1)
            cl.addWidget(date_lbl)

            self.achievements_container.addWidget(card)

            # Newly unlocked achievement presentation feedback
            if aid in newly_unlocked_ids:
                if not is_reduced_motion_enabled():
                    effect = QGraphicsOpacityEffect(card)
                    card.setGraphicsEffect(effect)
                    anim = QPropertyAnimation(effect, b"opacity", card)
                    anim.setDuration(350)
                    anim.setStartValue(0.0)
                    anim.setEndValue(1.0)
                    anim.setEasingCurve(QEasingCurve.OutCubic)
                    card._fade_anim = anim
                    anim.start()

                from UI.components.toast_notification import ToastNotification
                ToastNotification.show_toast(
                    self,
                    "ACHIEVEMENT UNLOCKED!",
                    f"{ach_info['icon']} {ach_info['name']}: {ach_info['description']}",
                    icon_str=ach_info["icon"],
                )

    def open_character_selector(self):
        """Open the non-destructive Character Selector dialog."""
        level = self.progression_service.get_current_level()
        dialog = CharacterSelectorDialog(self.character_manager, current_level=level, parent=self)
        dialog.character_changed.connect(self._on_character_changed)
        dialog.exec()

    def _on_character_changed(self, new_character_id):
        """Refresh page and notify app shell when character identity changes."""
        self.refresh()

    def open_achievement_library(self):
        """Open the dedicated Achievement Library modal."""
        ach_mgr = self.progression_service.achievement_manager
        dialog = AchievementLibraryDialog(ach_mgr, parent=self)
        dialog.exec()
