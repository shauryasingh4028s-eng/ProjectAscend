"""Focus Mode: a dedicated, distraction-free concentration environment.

Timer behaviour, pause/resume and completion are owned entirely by the
existing SessionEngine. This module only presents that state.
"""

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from UI.theme.design_system import (
    ButtonFactory,
    Colors,
    IconFactory,
    Spacing,
    ThemeManager,
)
from UI.theme.motion_utils import is_reduced_motion_enabled


class CircularTimer(QWidget):
    """Custom-painted ring showing session progress around the elapsed time."""

    def __init__(self):
        super().__init__()
        self.progress = 0.0
        self.time_text = "00:00:00"
        self.caption_text = "Focus Time"
        self.setFixedSize(288, 288)

    def set_progress(self, progress):
        self.progress = max(0.0, min(float(progress), 1.0))
        self.update()

    def set_time_text(self, text):
        self.time_text = text
        self.update()

    def set_caption(self, text):
        self.caption_text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        thickness = 12
        inset = thickness // 2 + 6
        rect = self.rect().adjusted(inset, inset, -inset, -inset)

        # Unfilled track.
        track_pen = QPen(QColor(Colors.SURFACE_ELEVATED))
        track_pen.setWidth(thickness)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)

        # Elapsed arc, drawn clockwise from the top.
        if self.progress > 0:
            arc_pen = QPen(QColor(Colors.PRIMARY))
            arc_pen.setWidth(thickness)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.drawArc(rect, 90 * 16, int(-self.progress * 360 * 16))

        # Caption above the time.
        painter.setPen(QColor(Colors.TEXT_MUTED))
        caption_font = painter.font()
        caption_font.setPointSize(9)
        caption_font.setWeight(QFont.DemiBold)
        painter.setFont(caption_font)
        painter.drawText(
            rect.adjusted(0, rect.height() // 2 - 58, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            self.caption_text.upper(),
        )

        # Elapsed time.
        painter.setPen(QColor(Colors.TEXT_PRIMARY))
        time_font = painter.font()
        time_font.setPointSize(30)
        time_font.setWeight(QFont.ExtraBold)
        painter.setFont(time_font)
        painter.drawText(rect, Qt.AlignCenter, self.time_text)


class FocusMode(QWidget):
    def __init__(self, activity, session_engine, dashboard):
        super().__init__()

        # Store the selected activity shown in Focus Mode.
        self.activity = activity

        # Use the existing SessionEngine from the Dashboard.
        # This keeps the timer synchronized and avoids creating another timer.
        self.session_engine = session_engine

        # Store the Dashboard so it can be refreshed after completion.
        self.dashboard = dashboard

        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        # Configure the Focus Mode window.
        self.setWindowTitle("Project Ascend Focus Mode")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)

        # Build the fullscreen distraction-free interface.
        self.apply_styles()
        self.build_ui()
        self.showFullScreen()
        self.animate_enter_transition()

        # Connect to the existing SessionEngine signals.
        self.session_engine.timer_updated.connect(self.update_timer)
        self.session_engine.session_paused.connect(self.show_paused_state)
        self.session_engine.session_resumed.connect(self.show_running_state)
        self.session_engine.session_completed.connect(self.close_after_complete)

        # Show the current timer value immediately.
        self.update_timer(self.session_engine.elapsed_seconds)

    def apply_styles(self):
        # Reuse the shared design system so Focus Mode matches the product.
        self.setStyleSheet(ThemeManager.app_stylesheet())

    def animate_enter_transition(self):
        """FOCUS-ENTER-01: Animate background color transition (~300ms) on entering Focus Mode."""
        if is_reduced_motion_enabled():
            return

        self.bg_anim = QVariantAnimation(self)
        self.bg_anim.setDuration(300)
        self.bg_anim.setStartValue(QColor("#030407"))
        self.bg_anim.setEndValue(QColor(Colors.BACKGROUND))
        self.bg_anim.setEasingCurve(QEasingCurve.OutCubic)

        def update_bg(color):
            palette = self.palette()
            palette.setColor(self.backgroundRole(), color)
            self.setPalette(palette)

        self.bg_anim.valueChanged.connect(update_bg)
        self.bg_anim.start()

    def build_ui(self):
        # Create the main layout for the fullscreen focus window.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(64, 48, 64, 48)
        main_layout.setSpacing(Spacing.XL)
        main_layout.setAlignment(Qt.AlignCenter)

        brand = QLabel("ASCEND")
        brand.setObjectName("SidebarSectionLabel")
        brand.setAlignment(Qt.AlignCenter)

        self.activity_name_label = QLabel(self.activity.name)
        self.activity_name_label.setAlignment(Qt.AlignCenter)
        self.activity_name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 28px; font-weight: 800;"
        )

        self.activity_type_label = QLabel(self.activity.activity_type)
        self.activity_type_label.setObjectName("MutedText")
        self.activity_type_label.setAlignment(Qt.AlignCenter)

        self.timer_ring = CircularTimer()

        ring_row = QHBoxLayout()
        ring_row.addStretch()
        ring_row.addWidget(self.timer_ring)
        ring_row.addStretch()

        self.estimated_minutes_label = QLabel(
            f"Planned: {self.activity.estimated_minutes} min"
        )
        self.estimated_minutes_label.setObjectName("MutedText")
        self.estimated_minutes_label.setAlignment(Qt.AlignCenter)

        self.pause_button = self.button_factory.secondary("Pause", "fa5s.pause")
        self.pause_button.clicked.connect(self.pause_or_resume_session)

        self.complete_button = self.button_factory.success("Complete", "fa5s.check")
        self.complete_button.clicked.connect(self.complete_session)

        self.exit_button = self.button_factory.secondary("Exit", "fa5s.times")
        self.exit_button.clicked.connect(self.close)

        control_row = QHBoxLayout()
        control_row.setSpacing(Spacing.MD)
        control_row.addStretch()
        for button in (self.pause_button, self.complete_button, self.exit_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumWidth(132)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            control_row.addWidget(button)
        control_row.addStretch()

        hint = QLabel("No distractions. Just progress.")
        hint.setObjectName("MutedText")
        hint.setAlignment(Qt.AlignCenter)

        main_layout.addStretch()
        main_layout.addWidget(brand)
        main_layout.addWidget(self.activity_name_label)
        main_layout.addWidget(self.activity_type_label)
        main_layout.addSpacing(Spacing.SM)
        main_layout.addLayout(ring_row)
        main_layout.addWidget(self.estimated_minutes_label)
        main_layout.addSpacing(Spacing.SM)
        main_layout.addLayout(control_row)
        main_layout.addWidget(hint)
        main_layout.addStretch()

    def update_timer(self, seconds):
        # Keep the Focus Mode timer synchronized with SessionEngine.
        formatted_time = self.session_engine.format_time(seconds)
        self.timer_ring.set_time_text(formatted_time)
        self.update_progress_bar(seconds)

    def update_progress_bar(self, seconds):
        # Show progress based on elapsed time compared with estimated time.
        estimated_seconds = self.activity.estimated_minutes * 60

        if estimated_seconds <= 0:
            progress_percent = 0
        else:
            progress_percent = int((seconds / estimated_seconds) * 100)

        if progress_percent > 100:
            progress_percent = 100

        self.timer_ring.set_progress(progress_percent / 100)

    def pause_or_resume_session(self):
        # Pause or resume using the existing SessionEngine.
        if self.session_engine.is_running:
            self.session_engine.pause()
        else:
            self.session_engine.resume()

    def complete_session(self):
        # Complete the activity using the existing SessionEngine.
        self.session_engine.complete()

    def show_paused_state(self):
        # Change the button text when the session is paused.
        self.pause_button.setText("Resume")
        self.timer_ring.set_caption("Paused")

    def show_running_state(self):
        # Change the button text when the session is running.
        self.pause_button.setText("Pause")
        self.timer_ring.set_caption("Focus Time")

    def close_after_complete(self, activity):
        # Refresh the Dashboard and close Focus Mode after completion.
        self.dashboard.load_today_activities()
        self.close()

    def keyPressEvent(self, event):
        # Pressing Esc exits Focus Mode without stopping the session.
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Disconnect signals so closed Focus Mode windows do not keep updating.
        try:
            self.session_engine.timer_updated.disconnect(self.update_timer)
            self.session_engine.session_paused.disconnect(
                self.show_paused_state
            )
            self.session_engine.session_resumed.disconnect(
                self.show_running_state
            )
            self.session_engine.session_completed.disconnect(
                self.close_after_complete
            )
        except RuntimeError:
            pass
        except TypeError:
            pass

        # FOCUS-ENTER-01: Animate exit background color transition (~300ms) unless reduced motion is active or already animated.
        if not getattr(self, "_exit_animated", False) and not is_reduced_motion_enabled():
            event.ignore()
            self.animate_exit_transition()
            return

        super().closeEvent(event)

    def animate_exit_transition(self):
        """FOCUS-ENTER-01: 300ms exit background color transition before window destruction."""
        if getattr(self, "_exiting", False):
            return

        self._exiting = True

        if hasattr(self, "bg_anim") and self.bg_anim is not None and self.bg_anim.state() == QVariantAnimation.Running:
            self.bg_anim.stop()

        self.exit_anim = QVariantAnimation(self)
        self.exit_anim.setDuration(300)
        self.exit_anim.setStartValue(QColor(Colors.BACKGROUND))
        self.exit_anim.setEndValue(QColor("#030407"))
        self.exit_anim.setEasingCurve(QEasingCurve.OutCubic)

        def update_bg(color):
            palette = self.palette()
            palette.setColor(self.backgroundRole(), color)
            self.setPalette(palette)

        def finalize_close():
            self._exit_animated = True
            self.close()

        self.exit_anim.valueChanged.connect(update_bg)
        self.exit_anim.finished.connect(finalize_close)
        self.exit_anim.start()
