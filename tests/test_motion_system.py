"""Test suite for Project Ascend motion system and reduced motion handling."""

import pytest
from PySide6.QtCore import QSettings
from UI.theme.motion_utils import is_reduced_motion_enabled, set_reduced_motion_enabled
from UI.components.toast_notification import ToastNotification


def test_reduced_motion_utility(qapp):
    # Test setting and reading reduced motion state
    set_reduced_motion_enabled(True)
    assert is_reduced_motion_enabled() is True

    set_reduced_motion_enabled(False)
    assert is_reduced_motion_enabled() is False


def test_toast_notification_lifecycle(qapp):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    parent.resize(800, 600)

    toast = ToastNotification.show_toast(parent, "Test Title", "Test Message")
    assert toast is not None
    assert toast.title_label.text() == "Test Title"
    assert toast.message_label.text() == "Test Message"

    # Updating active toast
    toast2 = ToastNotification.show_toast(parent, "Updated Title", "Updated Message")
    assert toast2 is toast
    assert toast.title_label.text() == "Updated Title"

    toast.dismiss()


def test_dashboard_greeting_date_gating(qapp, database):
    from Modules.dashboard_v2 import DashboardV2
    dashboard = DashboardV2(database)
    app_settings = QSettings("ProjectAscend", "ProjectAscend")

    # Set last_greeting_date to today
    from datetime import date
    today_str = date.today().isoformat()
    app_settings.setValue("last_greeting_date", today_str)

    # Calling check_daily_greeting when date is today should not overwrite last_greeting_date
    dashboard.check_daily_greeting()
    assert app_settings.value("last_greeting_date", "", type=str) == today_str
