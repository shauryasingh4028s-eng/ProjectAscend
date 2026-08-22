"""Settings page.

Deliberately quiet: clear sections, consistent controls and no decoration.
The only persisted value it writes is the existing daily goal, using the
existing Database API.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QComboBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from Modules.insights_service import format_minutes
from UI.theme.design_system import IconFactory, ButtonFactory, Spacing, ThemeManager


class SettingsSection(QFrame):
    """A titled settings panel holding one or more rows."""

    def __init__(self, title, description=""):
        super().__init__()
        self.setObjectName("InsightSurface")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(
            Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG
        )
        self.layout.setSpacing(Spacing.SM)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.layout.addWidget(title_label)

        if description:
            description_label = QLabel(description)
            description_label.setObjectName("MutedText")
            description_label.setWordWrap(True)
            self.layout.addWidget(description_label)

    def add_row(self, widget):
        self.layout.addWidget(widget)


class SettingsPage(QWidget):
    """Lets the user adjust the existing daily focus goal."""

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

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(Spacing.XXL, Spacing.XL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.LG)

        profile_section = SettingsSection(
            "Profile",
            "Choose the name shown in your Ascend sidebar.",
        )
        profile_row = QWidget()
        profile_layout = QHBoxLayout(profile_row)
        profile_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        profile_layout.setSpacing(Spacing.MD)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name")
        self.name_input.setMaxLength(32)
        self.name_input.setFixedWidth(240)
        self.name_save_button = self.button_factory.primary("Save Name", "fa5s.user")
        self.name_save_button.clicked.connect(self.save_name)
        profile_layout.addWidget(self.name_input)
        profile_layout.addStretch()
        profile_layout.addWidget(self.name_save_button)
        profile_section.add_row(profile_row)
        self.name_status = QLabel()
        self.name_status.setObjectName("MutedText")
        self.name_status.setVisible(False)
        profile_section.add_row(self.name_status)

        theme_section = SettingsSection(
            "Appearance",
            "Switch between the dark Ascend interface and a clean light theme.",
        )
        theme_row = QWidget()
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        theme_layout.setSpacing(Spacing.MD)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setFixedWidth(180)
        self.theme_combo.currentIndexChanged.connect(self.save_theme)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        theme_section.add_row(theme_row)

        goal_section = SettingsSection(
            "Daily Focus Goal",
            "The amount of focused time that counts as a successful day. "
            "Streaks and daily goal insights use this value.",
        )

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        row_layout.setSpacing(Spacing.MD)

        self.goal_input = QSpinBox()
        self.goal_input.setMinimum(30)
        self.goal_input.setMaximum(1440)
        self.goal_input.setSingleStep(15)
        self.goal_input.setSuffix(" min")
        self.goal_input.setFixedWidth(130)
        self.goal_input.valueChanged.connect(self.update_preview)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("MutedText")

        self.save_button = self.button_factory.primary("Save", "fa5s.save")
        self.save_button.clicked.connect(self.save_daily_goal)

        row_layout.addWidget(self.goal_input)
        row_layout.addWidget(self.preview_label)
        row_layout.addStretch()
        row_layout.addWidget(self.save_button)
        goal_section.add_row(row)

        self.status_label = QLabel()
        self.status_label.setObjectName("MutedText")
        self.status_label.setVisible(False)
        goal_section.add_row(self.status_label)

        about_section = SettingsSection(
            "About",
            "Project Ascend — Focus. Progress. Ascend.\n"
            "Your activities, focus sessions and XP are stored locally.",
        )

        privacy_section = SettingsSection(
            "Privacy & Analytics",
            "Ascend collects anonymous product usage data by default to "
            "help improve the application. This data helps understand which "
            "features are used and how often — it never includes your "
            "name, email, task names or content, school information, file "
            "paths, precise location, or any personal data.\n\n"
            "All data is associated with a random installation ID — not "
            "your identity. Analytics is enabled by default and can be "
            "disabled at any time.",
        )
        privacy_row = QWidget()
        privacy_layout = QHBoxLayout(privacy_row)
        privacy_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        privacy_layout.setSpacing(Spacing.MD)
        self.analytics_checkbox = QCheckBox(
            "Share anonymous usage data to help improve Ascend"
        )
        self.analytics_checkbox.stateChanged.connect(self._on_analytics_toggled)
        privacy_layout.addWidget(self.analytics_checkbox)
        privacy_layout.addStretch()
        privacy_section.add_row(privacy_row)
        self.analytics_status = QLabel()
        self.analytics_status.setObjectName("MutedText")
        self.analytics_status.setWordWrap(True)
        privacy_section.add_row(self.analytics_status)

        layout.addWidget(profile_section)
        layout.addWidget(theme_section)
        layout.addWidget(goal_section)
        layout.addWidget(privacy_section)
        layout.addWidget(about_section)
        layout.addStretch()

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def load_settings(self):
        self.goal_input.setValue(self.database.get_daily_goal())
        name = self.app_settings.value("display_name", "Ascender", type=str).strip() or "Ascender"
        self.name_input.setText(name)
        theme = self.app_settings.value("theme", "dark", type=str)
        index = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        # Load analytics consent state (defaults to True for fresh installation)
        consented = self.app_settings.value("telemetry/consented", True, type=bool)
        self.analytics_checkbox.blockSignals(True)
        self.analytics_checkbox.setChecked(consented)
        self.analytics_checkbox.blockSignals(False)
        self._update_analytics_status(consented)
        self.update_preview()

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
        self.preview_label.setText(
            f"Equivalent to {format_minutes(self.goal_input.value())} of focus."
        )

    def save_daily_goal(self):
        value = self.goal_input.value()
        self.database.set_daily_goal(value)
        # Reload so the field always mirrors the clamped, persisted value.
        self.goal_input.setValue(self.database.get_daily_goal())
        self.status_label.setText(
            f"Daily goal saved as {format_minutes(self.goal_input.value())}."
        )
        self.status_label.setVisible(True)
        self.daily_goal_changed.emit(self.goal_input.value())

    def _on_analytics_toggled(self, state):
        """Handle analytics opt-in/opt-out toggle.

        When enabled: consent is recorded; the AppController's telemetry
        client (if it exists) is notified.
        When disabled: consent is revoked and the local queue is purged.
        """
        consented = bool(state)
        self.app_settings.setValue("telemetry/consented", consented)
        self.app_settings.sync()
        self._update_analytics_status(consented)

        # Notify the telemetry client if the app controller has one.
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                # Walk up to find the AppController (it owns the SettingsPage).
                controller = getattr(app, "_ascend_controller", None)
                if controller is not None and hasattr(controller, "telemetry") and controller.telemetry is not None:
                    if consented:
                        controller.telemetry.enable()
                    else:
                        controller.telemetry.disable()
        except Exception:
            # Analytics toggle must never break the Settings page.
            pass

    def _update_analytics_status(self, consented):
        """Update the status label below the analytics checkbox."""
        if consented:
            self.analytics_status.setText(
                "Anonymous usage data is being shared. Thank you for "
                "helping improve Ascend."
            )
        else:
            self.analytics_status.setText(
                "Anonymous usage data is not being shared. No data is "
                "collected or sent."
            )
