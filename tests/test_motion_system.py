"""Test suite for Project Ascend motion system and reduced motion handling."""

from datetime import date
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

    today_str = date.today().isoformat()
    app_settings.setValue("last_greeting_date", today_str)

    # Calling check_daily_greeting when date is today should not overwrite last_greeting_date
    dashboard.check_daily_greeting()
    assert app_settings.value("last_greeting_date", "", type=str) == today_str


def test_focus_mode_enter_and_exit_transitions(qapp, database):
    import warnings
    from PySide6.QtTest import QTest
    from Modules.activity import Activity
    from Modules.dashboard_v2 import DashboardV2
    from Modules.focus_mode import FocusMode
    from Modules.session import SessionEngine

    activity = Activity(id=1, name="Test Focus", activity_type="Study", estimated_minutes=30, date=date.today().isoformat())
    dashboard = DashboardV2(database)
    engine = SessionEngine(database)

    # 1. Motion enabled: enter & exit animations run and update background styleSheet dynamically without disconnect warnings
    set_reduced_motion_enabled(False)
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")

        focus = FocusMode(activity, engine, dashboard)
        assert focus is not None
        assert hasattr(focus, "bg_anim")
        assert focus.bg_anim.duration() == 1000

        # Step event loop for enter transition (~1000ms)
        QTest.qWait(1050)
        assert focus._bg_color_hex.lower() == "#05070c"

        # Trigger exit transition (~1000ms)
        focus.close()
        QTest.qWait(1050)

        # Ensure no libpyside disconnect warnings occurred
        disconnect_warnings = [
            w for w in recorded_warnings
            if "Failed to disconnect" in str(w.message)
        ]
        assert len(disconnect_warnings) == 0

    # 2. Reduced motion active: enter transition skipped and exit transition closes directly
    set_reduced_motion_enabled(True)
    focus_rm = FocusMode(activity, engine, dashboard)
    assert focus_rm is not None
    focus_rm.close()
    set_reduced_motion_enabled(False)


def test_approved_animation_durations(qapp, database):
    from PySide6.QtWidgets import QWidget, QPushButton
    from UI.components.dashboard_widgets import ActivityCard, ProgressCard, HeroCard
    from UI.theme.design_system import IconFactory
    from Modules.activity import Activity
    from Modules.dashboard_v2 import DashboardV2

    set_reduced_motion_enabled(False)
    dummy_widget = QWidget()
    icon_factory = IconFactory(dummy_widget)
    act = Activity(id=1, name="Test Task", activity_type="Study", estimated_minutes=30, date=date.today().isoformat())

    # TASK-CHECK-01 (300ms)
    from PySide6.QtWidgets import QPushButton
    card = ActivityCard(act, icon_factory, QPushButton("Menu"))
    card.animate_check_icon()
    assert card.icon_anim is not None
    assert card.icon_anim.duration() == 300

    # GOAL-COMPLETE-01 (900ms)
    pcard = ProgressCard(icon_factory)
    pcard.animate_goal_completion()
    assert pcard.goal_anim is not None
    assert pcard.goal_anim.duration() == 900

    # DASH-GREET-01 (500ms)
    btn = QPushButton("Settings")
    hero = HeroCard(btn, "Good evening")
    hero.animate_greeting()
    assert hero.greeting_anim is not None
    assert hero.greeting_anim.duration() == 500

    # DASH-PROGRESS-01 (700ms)
    dash = DashboardV2(database)
    dash.animate_progress_bar(dash.progress_bar, 50)
    assert dash.progress_animation is not None
    assert dash.progress_animation.duration() == 700

    set_reduced_motion_enabled(False)

