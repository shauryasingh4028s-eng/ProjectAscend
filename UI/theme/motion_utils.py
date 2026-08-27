"""Motion utilities and reduced-motion preference handling for Project Ascend.

Provides lightweight reduced-motion checks, motion constants, and safe animation helpers.
When reduced motion is active, animations apply final target state directly
without instantiating running QPropertyAnimation / QVariantAnimation loops.
"""

from datetime import date

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSettings,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QScrollArea, QWidget


# Motion Durations (ms)
MICRO_INTERACTION_DURATION = 300
SCROLL_REVEAL_DURATION = 450
HERO_GREETING_DURATION = 500
CHART_BAR_DURATION = 600
CHART_TREND_DURATION = 700
CELEBRATION_DURATION = 900


HERO_DAILY_MESSAGES = (
    "Stay focused. Keep ascending.",
    "Small progress compounds.",
    "Make today count.",
    "One focused session at a time.",
    "Keep the momentum.",
    "Build the habit. Trust the process.",
    "Focus creates momentum.",
    "Show up. Move forward.",
    "Progress starts with consistency.",
    "Do the work that moves you forward.",
    "Consistency turns effort into growth.",
    "Focus on the next step.",
    "Clear goals, clear mind.",
    "Master your time, master your day.",
    "Quality focus over quantity.",
    "Small wins lead to big breakthroughs.",
)


def get_daily_hero_message(target_date: date = None) -> str:
    """Return a deterministic Project Ascend motivational message for any date."""
    if target_date is None:
        target_date = date.today()
    index = target_date.toordinal() % len(HERO_DAILY_MESSAGES)
    return HERO_DAILY_MESSAGES[index]


def is_reduced_motion_enabled() -> bool:
    """Return True if the user has requested reduced motion."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    return settings.value("reduced_motion", False, type=bool)


def set_reduced_motion_enabled(enabled: bool) -> None:
    """Persist the reduced motion preference."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("reduced_motion", bool(enabled))
    settings.sync()


class ScrollRevealManager(QObject):
    """Viewport-based component entrance controller.

    Monitors a QScrollArea's viewport and triggers smooth, subtle entrance motion
    (opacity 0 -> 1) when registered target cards scroll into view.
    """

    def __init__(self, scroll_area: QScrollArea):
        super().__init__(scroll_area)
        self.scroll_area = scroll_area
        self.registered_widgets = []
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(30)  # ~30ms throttle tick
        self._throttle_timer.timeout.connect(self.check_viewport_reveals)

        # Connect scrollbar value changes
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def register_widget(self, widget: QWidget) -> None:
        """Register a component container card for scroll reveal."""
        if widget and widget not in self.registered_widgets:
            self.registered_widgets.append(widget)
            # Perform immediate check for initial viewport contents
            QTimer.singleShot(50, self.check_viewport_reveals)

    def _on_scroll(self, _value: int) -> None:
        if not self._throttle_timer.isActive():
            self._throttle_timer.start()

    def check_viewport_reveals(self) -> None:
        if not self.scroll_area or not self.scroll_area.viewport():
            return

        viewport = self.scroll_area.viewport()
        viewport_rect = viewport.rect()

        for widget in list(self.registered_widgets):
            if not widget or getattr(widget, "_has_revealed", False):
                continue

            try:
                pos_in_viewport = widget.mapTo(viewport, QPoint(0, 0))
                widget_rect = QRect(pos_in_viewport, widget.size())
            except Exception:
                continue

            if viewport_rect.intersects(widget_rect):
                widget._has_revealed = True
                self.animate_reveal(widget)

    def animate_reveal(self, widget: QWidget) -> None:
        if is_reduced_motion_enabled():
            if widget.graphicsEffect() is not None:
                widget.setGraphicsEffect(None)
            return

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(SCROLL_REVEAL_DURATION)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        widget._reveal_anim = anim
        anim.start()
