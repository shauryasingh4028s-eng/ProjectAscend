from PySide6.QtCore import Qt, QPropertyAnimation, QTimer, QEasingCurve, QRect
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor

from UI.theme.design_system import Colors, Spacing
from UI.theme.motion_utils import MotionUtils

class ToastNotification(QWidget):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowTransparentForInput | Qt.WA_ShowWithoutActivating | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setObjectName("ToastNotification")
        self.setStyleSheet(f"""
            QWidget#ToastNotification {{
                background-color: {Colors.SURFACE_ELEVATED};
                border: 1px solid {Colors.BORDER_STRONG};
                border-radius: 8px;
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        icon_label = QLabel("🚀")

        text_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        msg_label = QLabel(message)

        text_layout.addWidget(title_label)
        text_layout.addWidget(msg_label)

        layout.addWidget(icon_label)
        layout.addLayout(text_layout)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        self.adjustSize()
        self.hide()

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(400)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_toast)

    def show_toast(self):
        parent_rect = self.parentWidget().rect()
        target_x = parent_rect.width() - self.width() - Spacing.XL
        target_y = parent_rect.height() - self.height() - Spacing.XL

        if MotionUtils.reduced_motion_enabled():
            self.setGeometry(target_x, target_y, self.width(), self.height())
            self.show()
            self.timer.start(3000)
            return

        start_rect = QRect(target_x, parent_rect.height() + 10, self.width(), self.height())
        end_rect = QRect(target_x, target_y, self.width(), self.height())

        self.setGeometry(start_rect)
        self.show()

        if self.animation.state() == QPropertyAnimation.Running:
            self.animation.stop()

        self.animation.setStartValue(start_rect)
        self.animation.setEndValue(end_rect)
        self.animation.finished.connect(self._on_show_finished)

        try:
            self.animation.finished.disconnect(self._on_hide_finished)
        except:
            pass

        self.animation.start()

    def _on_show_finished(self):
        self.timer.start(3000)

    def hide_toast(self):
        if MotionUtils.reduced_motion_enabled():
            self.hide()
            self.deleteLater()
            return

        parent_rect = self.parentWidget().rect()
        target_x = self.geometry().x()
        target_y = parent_rect.height() + 10

        end_rect = QRect(target_x, target_y, self.width(), self.height())

        if self.animation.state() == QPropertyAnimation.Running:
            self.animation.stop()

        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(end_rect)
        try:
            self.animation.finished.disconnect(self._on_show_finished)
        except:
            pass

        self.animation.finished.connect(self._on_hide_finished)
        self.animation.start()

    def _on_hide_finished(self):
        self.hide()
        self.deleteLater()
