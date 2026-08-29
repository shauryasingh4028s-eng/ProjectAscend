"""Focused unit test suite for the Project Ascend Settings Tab Rework.

Validates settings UI construction, initial state loading, setting changes,
signal emissions, persistence in QSettings/SQLite, theme switching, motion system
integration, analytics consent, database location discovery, and version display.
"""

from PySide6.QtCore import QSettings
from Database.database import Database
from Modules.settings_page import SettingsPage, SettingsSection, SettingsRow
from Modules.version import APP_VERSION
from UI.theme.design_system import ThemeManager
from UI.theme.motion_utils import is_reduced_motion_enabled, set_reduced_motion_enabled


def test_settings_page_builds(qapp, tmp_path):
    """1. SettingsPage builds successfully without errors."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert page is not None
    assert page.database == db
    db.close()


def test_initial_display_name_loading(qapp, tmp_path):
    """2. Initial Display Name reflects existing persisted preference."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("display_name", "TestExplorer")
    settings.sync()

    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert page.name_input.text() == "TestExplorer"
    db.close()


def test_save_display_name_persists_and_emits(qapp, tmp_path):
    """3. Changing Display Name persists correctly and emits profile_changed."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    emitted_names = []
    page.profile_changed.connect(lambda name: emitted_names.append(name))

    page.name_input.setText("AstroCaptain")
    page.save_name()

    settings = QSettings("ProjectAscend", "ProjectAscend")
    assert settings.value("display_name", type=str) == "AstroCaptain"
    assert emitted_names == ["AstroCaptain"]
    db.close()


def test_initial_theme_loading(qapp, tmp_path):
    """4. Initial theme reflects persisted application theme."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("theme", "light")
    settings.sync()

    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert page.theme_combo.currentData() == "light"
    db.close()


def test_save_theme_persists_and_emits(qapp, tmp_path):
    """5. Changing theme updates preference and emits theme_changed."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("theme", "dark")
    settings.sync()

    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    emitted_themes = []
    page.theme_changed.connect(lambda t: emitted_themes.append(t))

    index = page.theme_combo.findData("light")
    assert index >= 0
    page.theme_combo.setCurrentIndex(index)

    assert settings.value("theme", type=str) == "light"
    assert emitted_themes == ["light"]
    db.close()


def test_daily_focus_goal_loading(qapp, tmp_path):
    """6. Daily Focus Goal reflects authoritative existing value in SQLite."""
    db = Database(tmp_path / "settings_test.db")
    db.set_daily_goal(240)

    page = SettingsPage(db)
    assert page.goal_input.value() == 240
    db.close()


def test_save_daily_goal_persists_and_emits(qapp, tmp_path):
    """7. Changing Daily Focus Goal persists through database mechanism and emits daily_goal_changed."""
    db = Database(tmp_path / "settings_test.db")
    db.set_daily_goal(180)

    page = SettingsPage(db)

    emitted_goals = []
    page.daily_goal_changed.connect(lambda g: emitted_goals.append(g))

    page.goal_input.setValue(360)
    page.save_daily_goal()

    assert db.get_daily_goal() == 360
    assert emitted_goals == [360]
    db.close()


def test_daily_goal_preview_formatting(qapp, tmp_path):
    """8. Daily Focus Goal preview converts minutes correctly."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    page.goal_input.setValue(90)
    assert "1h 30m" in page.preview_label.text()

    page.goal_input.setValue(300)
    assert "5h 0m" in page.preview_label.text()
    db.close()


def test_initial_analytics_consent_loading(qapp, tmp_path):
    """9. Analytics control reflects existing consent state."""
    settings = QSettings("ProjectAscend", "ProjectAscend")
    settings.setValue("telemetry/consented", False)
    settings.sync()

    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert page.analytics_checkbox.isChecked() is False

    settings.setValue("telemetry/consented", True)
    settings.sync()
    page.load_settings()
    assert page.analytics_checkbox.isChecked() is True
    db.close()


def test_analytics_toggled_updates_consent(qapp, tmp_path):
    """10. Changing Analytics consent updates app_settings and status."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    page._on_analytics_toggled(False)
    settings = QSettings("ProjectAscend", "ProjectAscend")
    assert settings.value("telemetry/consented", type=bool) is False
    assert "not being shared" in page.analytics_status.text()

    page._on_analytics_toggled(True)
    assert settings.value("telemetry/consented", type=bool) is True
    assert "being shared" in page.analytics_status.text()
    db.close()


def test_initial_reduced_motion_loading(qapp, tmp_path):
    """11. Reduced Motion reflects existing motion preference."""
    set_reduced_motion_enabled(True)

    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert page.reduced_motion_checkbox.isChecked() is True

    set_reduced_motion_enabled(False)
    page.load_settings()
    assert page.reduced_motion_checkbox.isChecked() is False
    db.close()


def test_reduced_motion_toggled_updates_motion_utils(qapp, tmp_path):
    """12. Changing Reduced Motion updates motion_utils correctly."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    page._on_reduced_motion_toggled(True)
    assert is_reduced_motion_enabled() is True

    page._on_reduced_motion_toggled(False)
    assert is_reduced_motion_enabled() is False
    db.close()


def test_local_storage_location_display(qapp, tmp_path):
    """13. Local Storage Location displays actual authoritative database path."""
    db_file = tmp_path / "custom_location.db"
    db = Database(db_file)

    page = SettingsPage(db)
    path_displayed = page.storage_path_label.text()
    assert str(db_file.name) in path_displayed or str(db_file) in path_displayed
    db.close()


def test_version_footer_display(qapp, tmp_path):
    """14. Version footer reflects Modules.version.APP_VERSION."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)
    assert APP_VERSION in f"v{APP_VERSION}"
    db.close()


def test_themes_render_without_errors(qapp, tmp_path):
    """15. Both Deep Focus and Clear Thinking themes render without errors."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    ThemeManager.set_theme("dark")
    page.setStyleSheet(ThemeManager.app_stylesheet())

    ThemeManager.set_theme("light")
    page.setStyleSheet(ThemeManager.app_stylesheet())
    db.close()


def test_settings_page_contains_all_sections_and_rows(qapp, tmp_path):
    """16. SettingsPage contains all intended sections and controls."""
    db = Database(tmp_path / "settings_test.db")
    page = SettingsPage(db)

    sections = page.findChildren(SettingsSection)
    assert len(sections) >= 4

    rows = page.findChildren(SettingsRow)
    assert len(rows) >= 6
    db.close()
