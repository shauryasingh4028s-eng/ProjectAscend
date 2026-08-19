"""Selective, non-blocking celebration animations for meaningful progress."""

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QPauseAnimation,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from Modules.gamification_config import CHARACTER_BY_ID
from UI.components.character_sprites import character_pixmap
from UI.theme.design_system import Spacing


@dataclass(frozen=True)
class Celebration:
    event_id: str
    title: str
    message: str
    tier: int = 2
    symbol: str = "+"
    character_id: str | None = None
    stage_identifier: str | None = None
    previous_stage_identifier: str | None = None


class CelebrationOverlay(QWidget):
    """Small premium toast with a serialized animation queue.

    It never blocks input and only animates events explicitly supplied by the
    progression coordinator. Duplicate event IDs are ignored for the lifetime
    of the application; persisted XP/unlock guards prevent repeats on restart.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CelebrationOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.queue = deque()
        self.current_event = None
        self.seen_event_ids = set()
        self.played_events = []
        self.animation_group = None

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.LG, Spacing.XXL, Spacing.LG)
        root.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        self.card = QFrame()
        self.card.setObjectName("CelebrationCard")
        self.card.setFixedWidth(390)
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(
            Spacing.LG,
            Spacing.MD,
            Spacing.LG,
            Spacing.MD,
        )
        card_layout.setSpacing(Spacing.MD)

        self.symbol_label = QLabel("+")
        self.symbol_label.setObjectName("CelebrationSymbol")
        self.symbol_label.setAlignment(Qt.AlignCenter)
        self.symbol_label.setFixedSize(42, 42)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("CelebrationTitle")
        self.message_label = QLabel()
        self.message_label.setObjectName("CelebrationMessage")
        self.message_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.message_label)

        card_layout.addWidget(self.symbol_label, alignment=Qt.AlignTop)
        card_layout.addLayout(text_layout, 1)
        row.addWidget(self.card)
        root.addLayout(row)

        self.opacity_effect = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        self.hide()

    def enqueue(self, celebration):
        if not isinstance(celebration, Celebration):
            return False
        if celebration.event_id in self.seen_event_ids:
            return False
        self.seen_event_ids.add(celebration.event_id)
        self.queue.append(celebration)
        if self.current_event is None:
            self._play_next()
        return True

    def _play_next(self):
        if not self.queue:
            self.current_event = None
            self.hide()
            return

        self.current_event = self.queue.popleft()
        event = self.current_event
        self.played_events.append(event.event_id)
        self.title_label.setText(event.title)
        self.message_label.setText(event.message)
        self._set_event_symbol(event, use_previous=True)
        self.card.setProperty("tier", str(max(1, min(3, event.tier))))
        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)

        self.show()
        self.raise_()
        self.opacity_effect.setOpacity(0.0)

        fade_in = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        fade_in.setDuration(220 if event.tier < 3 else 280)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)

        hold_duration = 900 if event.tier == 1 else 1250
        if event.tier >= 3:
            hold_duration = 1800
        hold = QPauseAnimation(hold_duration, self)

        fade_out = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        fade_out.setDuration(240)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)

        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addAnimation(hold)
        group.addAnimation(fade_out)
        group.finished.connect(self._finish_current)
        self.animation_group = group
        group.start()

        if (
            event.character_id
            and event.previous_stage_identifier
            and event.previous_stage_identifier != event.stage_identifier
        ):
            # A rare evolution briefly shows the prior stage before revealing
            # the newly earned visual. The event ID guard prevents stale timers
            # from changing a later celebration.
            QTimer.singleShot(
                420,
                lambda event_id=event.event_id: self._reveal_evolved_character(
                    event_id
                ),
            )

    def _set_event_symbol(self, event, use_previous=False):
        character = CHARACTER_BY_ID.get(event.character_id)
        if character is None:
            self.symbol_label.setPixmap(QPixmap())
            self.symbol_label.setText(event.symbol)
            return

        stage = event.stage_identifier or "stage_1"
        if use_previous and event.previous_stage_identifier:
            stage = event.previous_stage_identifier
        self.symbol_label.setText("")
        self.symbol_label.setPixmap(character_pixmap(character, stage, 40))

    def _reveal_evolved_character(self, event_id):
        if self.current_event is None or self.current_event.event_id != event_id:
            return
        self._set_event_symbol(self.current_event, use_previous=False)

    def _finish_current(self):
        self.current_event = None
        self.animation_group = None
        QTimer.singleShot(80, self._play_next)

    def finish_immediately(self):
        """Safe fallback used during shutdown and deterministic UI tests."""
        if self.animation_group is not None:
            self.animation_group.stop()
        self.queue.clear()
        self.current_event = None
        self.opacity_effect.setOpacity(0.0)
        self.hide()
