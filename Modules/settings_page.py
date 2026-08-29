"""Settings page for Project Ascend.

Provides a calm, intentional, and production-grade settings experience centered around
"Control how Project Ascend feels, behaves, and accommodates you."

All controls reflect real, persisted application state across QSettings and SQLite.
"""

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Modules.insights_service import format_minutes
from Modules.version import APP_VERSION
from UI.theme.design_system import (
    ButtonFactory,
    Colors,
    IconFactory,
    Radius,
    Spacing,
    Typography,
)


class SettingsRow(QFrame):
    """A single setting row with icon, title, description, and right-aligned control."""

    def __init__(
        self,
        title: str,
        description: str,
        control_widget: QWidget,
        icon_name: str = None,
        icon_factory: IconFactory = None,
        is_last: bool = False,
    ):
        super().__init__()
        self.setObjectName("SettingsRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        if is_last:
            self.setStyleSheet("QFrame#SettingsRow { border-bottom: none; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.MD + 2)
        layout.setSpacing(Spacing.LG)

        # Left container (icon + text)
        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Spacing.MD)

        if icon_name and icon_factory:
            icon_badge = QLabel()
            icon_badge.setFixedSize(34, 34)
            icon_badge.setAlignment(Qt.AlignCenter)
            icon_badge.setObjectName("SettingsRowIcon")
            pix = icon_factory.get(icon_name, Colors.PRIMARY).pixmap(18, 18)
            icon_badge.setPixmap(pix)
            left_layout.addWidget(icon_badge)

        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("SettingTitle")

        desc_label = QLabel(description)
        desc_label.setObjectName("MutedText")
        desc_label.setWordWrap(True)

        text_layout.addWidget(title_label)
        text_layout.addWidget(desc_label)

        left_layout.addWidget(text_container)
        layout.addWidget(left_widget, 1)

        # Right container (control widget)
        if control_widget:
            layout.addWidget(control_widget, 0, Qt.AlignRight | Qt.AlignVCenter)


class SettingsSection(QWidget):
    """A titled section container wrapping one or more settings rows in an elevated card."""

    def __init__(self, title: str, description: str = ""):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, Spacing.MD)
        main_layout.setSpacing(Spacing.SM)

        # Section Header
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 2)
        header_layout.setSpacing(2)

        header_label = QLabel(title.upper())
        header_label.setObjectName("SettingsSectionHeader")
        header_layout.addWidget(header_label)

        if description:
            subheader_label = QLabel(description)
            subheader_label.setObjectName("SettingsSectionSubheader")
            subheader_label.setWordWrap(True)
            header_layout.addWidget(subheader_label)

        main_layout.addWidget(header_widget)

        # Section Card Container
        self.card = QFrame()
        self.card.setObjectName("SettingsSectionCard")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        main_layout.addWidget(self.card)

    def add_row(self, widget: QWidget):
        """Add a row or custom widget directly into the section card."""
        self.card_layout.addWidget(widget)


class SettingsPage(QWidget):
    """Main Settings page for Project Ascend."""

    daily_goal_changed = Signal(int)
    profile_changed = Signal(str)
    theme_changed = Signal(str)

    def __init__(self, database):
        super().__init__()
        self.database = database
        self.app_settings = QSettings("ProjectAscend", "ProjectAscend")
        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        self.build_ui()
        self.load_settings()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("PageBody")
        scroll_layout = QHBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)

        # Center content layout with maximum width constraint (~960px)
        content_container = QWidget()
        content_container.setMaximumWidth(960)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(Spacing.XL)

        # ── Page Header ──
        page_header = QWidget()
        header_layout = QVBoxLayout(page_header)
        header_layout.setContentsMargins(0, 0, 0, Spacing.SM)
        header_layout.setSpacing(Spacing.XS)

        title_label = QLabel("SETTINGS")
        title_label.setObjectName("PageTitle")

        subtitle_label = QLabel("Control how Project Ascend feels, behaves, and accommodates you.")
        subtitle_label.setObjectName("MutedText")

        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        content_layout.addWidget(page_header)

        # ── SECTION 1 — EXPERIENCE ──
        exp_section = SettingsSection(
            "Experience",
            "Personalize your display identity and visual theme.",
        )

        # Row 1: Display Name
        name_control = QWidget()
        name_ctrl_layout = QHBoxLayout(name_control)
        name_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        name_ctrl_layout.setSpacing(Spacing.SM)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name")
        self.name_input.setMaxLength(32)
        self.name_input.setFixedWidth(200)
        self.name_input.returnPressed.connect(self.save_name)

        self.name_save_button = self.button_factory.primary("Save", "fa5s.check")
        self.name_save_button.setFixedWidth(80)
        self.name_save_button.clicked.connect(self.save_name)

        name_ctrl_layout.addWidget(self.name_input)
        name_ctrl_layout.addWidget(self.name_save_button)

        row_name = SettingsRow(
            title="Display Name",
            description="The name displayed in your Ascend sidebar and greetings.",
            control_widget=name_control,
            icon_name="fa5s.user",
            icon_factory=self.icon_factory,
        )
        exp_section.add_row(row_name)

        self.name_status = QLabel()
        self.name_status.setObjectName("MutedText")
        self.name_status.setContentsMargins(Spacing.LG, 0, Spacing.LG, Spacing.SM)
        self.name_status.setVisible(False)
        exp_section.add_row(self.name_status)

        # Row 2: Appearance
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark — Deep Focus", "dark")
        self.theme_combo.addItem("Light — Clear Thinking", "light")
        self.theme_combo.setFixedWidth(200)
        self.theme_combo.currentIndexChanged.connect(self.save_theme)

        row_theme = SettingsRow(
            title="Appearance",
            description="Choose how Project Ascend looks across dark and light themes.",
            control_widget=self.theme_combo,
            icon_name="fa5s.palette",
            icon_factory=self.icon_factory,
            is_last=True,
        )
        exp_section.add_row(row_theme)
        content_layout.addWidget(exp_section)

        # ── SECTION 2 — FOCUS & FEEDBACK ──
        focus_section = SettingsSection(
            "Focus & Feedback",
            "Configure daily focus commitments and usage reporting.",
        )

        # Row 3: Daily Focus Goal
        goal_control = QWidget()
        goal_ctrl_layout = QHBoxLayout(goal_control)
        goal_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        goal_ctrl_layout.setSpacing(Spacing.MD)

        self.goal_input = QSpinBox()
        self.goal_input.setMinimum(30)
        self.goal_input.setMaximum(1440)
        self.goal_input.setSingleStep(15)
        self.goal_input.setSuffix(" min")
        self.goal_input.setFixedWidth(110)
        self.goal_input.valueChanged.connect(self.update_preview)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("MutedText")

        self.save_button = self.button_factory.primary("Save Goal", "fa5s.save")
        self.save_button.setFixedWidth(100)
        self.save_button.clicked.connect(self.save_daily_goal)

        goal_ctrl_layout.addWidget(self.preview_label)
        goal_ctrl_layout.addWidget(self.goal_input)
        goal_ctrl_layout.addWidget(self.save_button)

        row_goal = SettingsRow(
            title="Daily Focus Goal",
            description="Your daily target for focus time, streaks, and insights.",
            control_widget=goal_control,
            icon_name="fa5s.bullseye",
            icon_factory=self.icon_factory,
        )
        focus_section.add_row(row_goal)

        self.status_label = QLabel()
        self.status_label.setObjectName("MutedText")
        self.status_label.setContentsMargins(Spacing.LG, 0, Spacing.LG, Spacing.SM)
        self.status_label.setVisible(False)
        focus_section.add_row(self.status_label)

        # Row 4: Usage Analytics
        self.analytics_checkbox = QCheckBox("Share anonymous usage data")
        self.analytics_checkbox.stateChanged.connect(self._on_analytics_toggled)

        row_analytics = SettingsRow(
            title="Usage Analytics",
            description="Control whether anonymous usage and performance metrics are shared to help improve Ascend.",
            control_widget=self.analytics_checkbox,
            icon_name="fa5s.chart-line",
            icon_factory=self.icon_factory,
            is_last=True,
        )
        focus_section.add_row(row_analytics)

        self.analytics_status = QLabel()
        self.analytics_status.setObjectName("MutedText")
        self.analytics_status.setWordWrap(True)
        self.analytics_status.setContentsMargins(Spacing.LG, 0, Spacing.LG, Spacing.SM)
        focus_section.add_row(self.analytics_status)

        content_layout.addWidget(focus_section)

        # ── SECTION 3 — ACCESSIBILITY ──
        access_section = SettingsSection(
            "Accessibility",
            "Adjust motion and animation settings for comfortable visual interaction.",
        )

        # Row 5: Reduced Motion
        self.reduced_motion_checkbox = QCheckBox("Reduce motion")
        self.reduced_motion_checkbox.stateChanged.connect(self._on_reduced_motion_toggled)

        row_motion = SettingsRow(
            title="Reduced Motion",
            description="Minimize animated transitions and UI motion effects across Project Ascend.",
            control_widget=self.reduced_motion_checkbox,
            icon_name="fa5s.running",
            icon_factory=self.icon_factory,
            is_last=True,
        )
        access_section.add_row(row_motion)
        content_layout.addWidget(access_section)

        # ── SECTION 4 — DATA & APPLICATION ──
        data_section = SettingsSection(
            "Data & Application",
            "Local database information and privacy transparency.",
        )

        # Row 6: Local Storage Location
        db_path = self.get_database_location()
        self.storage_path_label = QLabel(db_path)
        self.storage_path_label.setObjectName("StoragePathBadge")
        self.storage_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        row_data = SettingsRow(
            title="Local Storage Location",
            description="Your activities, focus sessions, and progress are stored locally on this machine.",
            control_widget=self.storage_path_label,
            icon_name="fa5s.database",
            icon_factory=self.icon_factory,
            is_last=True,
        )
        data_section.add_row(row_data)
        content_layout.addWidget(data_section)

        # ── APPLICATION FOOTER ──
        footer_widget = QWidget()
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, Spacing.XL, 0, Spacing.LG)
        footer_layout.setSpacing(2)
        footer_layout.setAlignment(Qt.AlignCenter)

        app_title_lbl = QLabel("PROJECT ASCEND")
        app_title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: 800; letter-spacing: 1.5px;"
        )

        version_lbl = QLabel(f"Version v{APP_VERSION}")
        version_lbl.setObjectName("MutedText")
        version_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-weight: 600;")

        caption_lbl = QLabel("Local-first productivity & focus tracking.")
        caption_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")

        footer_layout.addWidget(app_title_lbl, 0, Qt.AlignCenter)
        footer_layout.addWidget(version_lbl, 0, Qt.AlignCenter)
        footer_layout.addWidget(caption_lbl, 0, Qt.AlignCenter)

        content_layout.addWidget(footer_widget)
        content_layout.addStretch()

        # Center horizontally with stretch margins
        scroll_layout.addStretch(1)
        scroll_layout.addWidget(content_container, 10)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        root_layout.addWidget(scroll_area)

    def get_database_location(self) -> str:
        """Return the authoritative local SQLite database file path."""
        try:
            if hasattr(self.database, "connection") and self.database.connection:
                cursor = self.database.connection.cursor()
                cursor.execute("PRAGMA database_list")
                row = cursor.fetchone()
                if row and len(row) >= 3 and row[2]:
                    return row[2]
        except Exception:
            pass

        appdata = os.getenv("LOCALAPPDATA", "")
        if appdata:
            return str(Path(appdata) / "ProjectAscend" / "Database" / "ascend.db")
        return "ascend.db"

    def load_settings(self):
        """Load persisted settings into the UI controls without triggering duplicate signals."""
        self.goal_input.blockSignals(True)
        self.goal_input.setValue(self.database.get_daily_goal())
        self.goal_input.blockSignals(False)

        name = self.app_settings.value("display_name", "Ascender", type=str).strip() or "Ascender"
        self.name_input.setText(name)

        theme = self.app_settings.value("theme", "dark", type=str)
        index = self.theme_combo.findData(theme)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.blockSignals(False)

        from UI.theme.motion_utils import is_reduced_motion_enabled

        self.reduced_motion_checkbox.blockSignals(True)
        self.reduced_motion_checkbox.setChecked(is_reduced_motion_enabled())
        self.reduced_motion_checkbox.blockSignals(False)

        consented = self.app_settings.value("telemetry/consented", True, type=bool)
        self.analytics_checkbox.blockSignals(True)
        self.analytics_checkbox.setChecked(consented)
        self.analytics_checkbox.blockSignals(False)
        self._update_analytics_status(consented)

        self.update_preview()

    def _on_reduced_motion_toggled(self, state):
        from UI.theme.motion_utils import set_reduced_motion_enabled

        is_checked = state == Qt.Checked or state == 2 or state is True
        set_reduced_motion_enabled(is_checked)

    def save_name(self):
        name = self.name_input.text().strip() or "Ascender"
        self.name_input.setText(name)
        self.app_settings.setValue("display_name", name)
        self.app_settings.sync()
        self.name_status.setText(f"Name saved as {name}.")
        self.name_status.setVisible(True)
        self.profile_changed.emit(name)

    def save_theme(self):
        theme = self.theme_combo.currentData() or "dark"
        self.app_settings.setValue("theme", theme)
        self.app_settings.sync()
        self.theme_changed.emit(theme)

    def update_preview(self):
        mins = self.goal_input.value()
        self.preview_label.setText(f"Equivalent to {format_minutes(mins)} of focus daily.")

    def save_daily_goal(self):
        value = self.goal_input.value()
        self.database.set_daily_goal(value)
        self.goal_input.setValue(self.database.get_daily_goal())
        self.status_label.setText(
            f"Daily goal saved as {format_minutes(self.goal_input.value())}."
        )
        self.status_label.setVisible(True)
        self.daily_goal_changed.emit(self.goal_input.value())

    def _on_analytics_toggled(self, state):
        consented = bool(state)
        self.app_settings.setValue("telemetry/consented", consented)
        self.app_settings.sync()
        self._update_analytics_status(consented)

        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                controller = getattr(app, "_ascend_controller", None)
                if (
                    controller is not None
                    and hasattr(controller, "telemetry")
                    and controller.telemetry is not None
                ):
                    if consented:
                        controller.telemetry.enable()
                    else:
                        controller.telemetry.disable()
        except Exception:
            pass

    def _update_analytics_status(self, consented: bool):
        if consented:
            self.analytics_status.setText(
                "Anonymous usage data is being shared. Thank you for helping improve Ascend."
            )
        else:
            self.analytics_status.setText(
                "Anonymous usage data is not being shared. No data is collected or sent."
            )
