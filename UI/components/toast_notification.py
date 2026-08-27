"""Non-blocking toast notifications for Project Ascend.

Used for milestone announcements such as LEVEL-UP-01.
Designed to be non-modal, non-blocking, and focus-safe.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QTimer, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from UI.theme.design_system import Colors, Spacing
from UI.theme.motion_utils import is_reduced_motion_enabled


class ToastNotification(QFrame):
    """Non-blocking, non-modal notification banner overlaying the application shell."""

    _active_toast = None  # Singleton reference to active toast to prevent stacking

    def __init__(self, parent_widget, title, message, icon_str="🚀"):
        super().__init__(parent_widget)
        self.setObjectName("ToastNotification")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        self.setStyleSheet(f"""
            QFrame#ToastNotification {{
                background-color: {Colors.SURFACE_ELEVATED};
                border: 1px solid {Colors.ACCENT};
                border-radius: 12px;
            }}
            QLabel#ToastTitle {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 800;
            }}
            QLabel#ToastMessage {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QLabel#ToastIcon {{
                font-size: 22px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        icon_label = QLabel(icon_str)
        icon_label.setObjectName("ToastIcon")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("ToastTitle")

        self.message_label = QLabel(message)
        self.message_label.setObjectName("ToastMessage")

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.message_label)

        layout.addWidget(icon_label)
        layout.addLayout(text_layout)

        self.adjustSize()
        self.setFixedWidth(max(280, self.sizeHint().width()))

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0 if is_reduced_motion_enabled() else 0.0)

        self.slide_anim = None
        self.fade_anim = None
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

    @classmethod
    def show_toast(cls, parent_widget, title, message, icon_str="🚀"):
        """Show a level-up or milestone toast, updating active toast if present."""
        if cls._active_toast is not None:
            try:
                cls._active_toast.update_content(title, message)
                cls._active_toast.restart_dismiss_timer()
                return cls._active_toast
            except RuntimeError:
                cls._active_toast = None

        toast = cls(parent_widget, title, message, icon_str)
        cls._active_toast = toast
        toast.start_presentation()
        return toast

    def update_content(self, title, message):
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            toast_width = max(280, self.sizeHint().width())
            self.setFixedWidth(toast_width)
            target_x = (parent.width() - toast_width) // 2
            self.move(target_x, 20)
            self.opacity_effect.setOpacity(1.0)

    def restart_dismiss_timer(self):
        self.dismiss_timer.stop()
        self.dismiss_timer.start(3500)

    def start_presentation(self):
        parent = self.parentWidget()
        if parent is None:
            self.show()
            return

        toast_width = self.width()
        toast_height = self.height()
        target_x = (parent.width() - toast_width) // 2
        target_y = 20

        start_y = -toast_height - 10

        self.move(target_x, target_y if is_reduced_motion_enabled() else start_y)
        self.show()
        self.raise_()

        if is_reduced_motion_enabled():
            self.move(target_x, target_y)
            self.opacity_effect.setOpacity(1.0)
            self.dismiss_timer.start(3500)
            return

        # Animate Y position (slide down, 600ms) and opacity (fade in, 450ms)
        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(600)
        self.slide_anim.setStartValue(self.pos())
        self.slide_anim.setEndValue(QRect(target_x, target_y, toast_width, toast_height).topLeft())
        self.slide_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(450)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)

        self.slide_anim.start()
        self.fade_anim.start()
        self.dismiss_timer.start(3500)

    def dismiss(self):
        if self.slide_anim is not None and self.slide_anim.state() == QPropertyAnimation.Running:
            self.slide_anim.stop()
        if self.fade_anim is not None and self.fade_anim.state() == QPropertyAnimation.Running:
            self.fade_anim.stop()

        if is_reduced_motion_enabled() or self.parentWidget() is None:
            self._cleanup()
            return

        toast_width = self.width()
        toast_height = self.height()
        target_x = self.x()
        target_y = -toast_height - 10

        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(500)
        self.slide_anim.setStartValue(self.pos())
        self.slide_anim.setEndValue(QRect(target_x, target_y, toast_width, toast_height).topLeft())
        self.slide_anim.setEasingCurve(QEasingCurve.InCubic)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)

        self.slide_anim.finished.connect(self._cleanup)
        self.slide_anim.start()
        self.fade_anim.start()

    def _cleanup(self):
        if self.slide_anim is not None and self.slide_anim.state() == QPropertyAnimation.Running:
            self.slide_anim.stop()
        if self.fade_anim is not None and self.fade_anim.state() == QPropertyAnimation.Running:
            self.fade_anim.stop()
        if ToastNotification._active_toast is self:
            ToastNotification._active_toast = None
        self.deleteLater()
