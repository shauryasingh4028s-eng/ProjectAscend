"""Test suite for Project Ascend motion system, reduced motion handling, and hero messages."""

from datetime import date, timedelta
import warnings
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget
from UI.theme.motion_utils import (
    HERO_DAILY_MESSAGES,
    ScrollRevealManager,
    get_daily_hero_message,
    is_reduced_motion_enabled,
    set_reduced_motion_enabled,
)
from UI.components.toast_notification import ToastNotification


def test_reduced_motion_utility(qapp):
    # Test setting and reading reduced motion state
    set_reduced_motion_enabled(True)
    assert is_reduced_motion_enabled() is True

    set_reduced_motion_enabled(False)
    assert is_reduced_motion_enabled() is False


def test_toast_notification_lifecycle(qapp):
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


def test_focus_mode_clean_lifecycle(qapp, database):
    from Modules.activity import Activity
    from Modules.dashboard_v2 import DashboardV2
    from Modules.focus_mode import FocusMode
    from Modules.session import SessionEngine

    activity = Activity(id=1, name="Test Focus", activity_type="Study", estimated_minutes=30, date=date.today().isoformat())
    dashboard = DashboardV2(database)
    engine = SessionEngine(database)

    set_reduced_motion_enabled(False)
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")

        focus = FocusMode(activity, engine, dashboard)
        assert focus is not None
        assert not hasattr(focus, "bg_anim")  # Focus animations removed per req 3

        # Immediate deterministic close without delay or exit animation
        focus.close()

        # Ensure no libpyside disconnect warnings occurred
        disconnect_warnings = [
            w for w in recorded_warnings
            if "Failed to disconnect" in str(w.message)
        ]
        assert len(disconnect_warnings) == 0


def test_chart_animations_progress_drawing(qapp):
    from Modules.analytics import ActivityDistributionChart, FocusTrendChart

    set_reduced_motion_enabled(False)

    # 1. FocusTrendChart (700ms)
    trend_chart = FocusTrendChart()
    trend_chart.set_points([])
    assert trend_chart._draw_progress == 0.0
    assert trend_chart.anim is not None
    assert trend_chart.anim.duration() == 700

    # 2. ActivityDistributionChart (600ms)
    dist_chart = ActivityDistributionChart()
    dist_chart.set_items([("Study", 60, 100)], 60)
    assert dist_chart._bar_progress == 0.0
    assert dist_chart.anim is not None
    assert dist_chart.anim.duration() == 600

    # 3. Reduced Motion
    set_reduced_motion_enabled(True)
    trend_chart.set_points([])
    assert trend_chart._draw_progress == 1.0

    dist_chart.set_items([("Study", 60, 100)], 60)
    assert dist_chart._bar_progress == 1.0

    set_reduced_motion_enabled(False)


def test_insights_no_scroll_reveals(qapp, database):
    from Modules.analytics import AnalyticsWindow
    from Modules.insights_service import InsightsService
    from Modules.streak_manager import StreakManager

    streak_mgr = StreakManager(database)
    service = InsightsService(database, streak_mgr)
    analytics = AnalyticsWindow(service)

    # Verify AnalyticsWindow does NOT have scroll_reveal_manager
    assert not hasattr(analytics, "scroll_reveal_manager")

    # Verify children inside content layout do NOT have scroll reveal triggers attached
    for i in range(analytics.content_layout.count()):
        item = analytics.content_layout.itemAt(i)
        w = item.widget()
        if w is not None:
            assert not hasattr(w, "_reveal_anim")


def test_dynamic_daily_hero_messages(qapp):
    from PySide6.QtWidgets import QPushButton
    from UI.components.dashboard_widgets import HeroCard

    assert len(HERO_DAILY_MESSAGES) >= 16

    today = date.today()
    tomorrow = today + timedelta(days=1)

    msg_today = get_daily_hero_message(today)
    msg_today_again = get_daily_hero_message(today)
    msg_tomorrow = get_daily_hero_message(tomorrow)

    # Same date produces identical message
    assert msg_today == msg_today_again
    assert isinstance(msg_today, str) and len(msg_today) > 0

    # Consecutive dates produce different messages
    assert msg_today != msg_tomorrow

    # HeroCard subtitle displays the daily message
    btn = QPushButton("Settings")
    hero = HeroCard(btn, "Good morning")
    assert hero.subtitle_label.text() == msg_today


def test_scroll_reveal_manager(qapp):
    scroll_area = QScrollArea()
    scroll_area.resize(400, 600)
    content = QWidget()
    layout = QVBoxLayout(content)

    card1 = QFrame()
    card1.setFixedHeight(200)
    card2 = QFrame()
    card2.setFixedHeight(200)

    layout.addWidget(card1)
    layout.addWidget(card2)
    scroll_area.setWidget(content)

    manager = ScrollRevealManager(scroll_area)

    set_reduced_motion_enabled(False)
    manager.register_widget(card1)
    manager.register_widget(card2)

    # Trigger viewport check directly
    manager.check_viewport_reveals()
    assert getattr(card1, "_has_revealed", False) is True

    # Reduced motion
    set_reduced_motion_enabled(True)
    card3 = QFrame()
    card3.setFixedHeight(200)
    layout.addWidget(card3)
    manager.register_widget(card3)
    manager.check_viewport_reveals()
    assert getattr(card3, "_has_revealed", False) is True

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
