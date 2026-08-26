from Modules.analytics import AnalyticsWindow
from Modules.capacity_service import CapacityService
from Modules.insights_service import InsightsService
from Modules.achievement_manager import AchievementManager
from Modules.xp_manager import XPManager
from Modules.streak_manager import StreakManager
from Modules.telemetry import AnalyticsClient
from Modules.version import APP_VERSION
from Database.database import Database
from Dialogs.daily_planner import DailyPlanner
from Modules.dashboard_v2 import Dashboard
from Modules.history import HistoryWindow
from Modules.player_progress import PlayerProgressPage
from Modules.settings_page import SettingsPage
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from UI.theme.design_system import ThemeManager
from UI.components.app_shell import AppShell

# XP required to advance one level, matching XPManager.get_level().
XP_PER_LEVEL = 100


class AppController:
    def __init__(self):
        self.app_settings = QSettings("ProjectAscend", "ProjectAscend")
        ThemeManager.set_theme(self.app_settings.value("theme", "dark", type=str))

        # Create one database connection shared by all screens.
        self.database = Database()

        self.streak_manager = StreakManager(self.database)

        self.xp_manager = XPManager(self.database)

        # Keep persisted-data aggregation outside all presentation widgets.
        self.insights_service = InsightsService(
            self.database,
            self.streak_manager,
        )

        self.achievement_manager = AchievementManager(
            self.database,
            self.streak_manager,
            self.xp_manager,
        )

        # Planned workload against the user's own stated available time.
        # Read-only over activities; the only value it ever writes is the
        # available time the user explicitly enters.
        self.capacity_service = CapacityService(self.database)

        # Create the dashboard for tracking today's activities.
        self.dashboard = Dashboard(self.database, self)

        # Create the planner for saving tomorrow's activities.
        self.tomorrow_planner = DailyPlanner(
            self.database,
            self,
            capacity_service=self.capacity_service,
        )

        # Create the history window for viewing previous productivity days.
        self.history_window = HistoryWindow(self.database)
        self.analytics_window = AnalyticsWindow(self.insights_service)
        self.player_progress_page = PlayerProgressPage(
            self.xp_manager,
            self.streak_manager,
        )
        self.settings_page = SettingsPage(self.database)
        self.settings_page.daily_goal_changed.connect(
            self.handle_daily_goal_changed
        )
        self.settings_page.profile_changed.connect(self.handle_profile_changed)
        self.settings_page.theme_changed.connect(self.handle_theme_changed)
        # Host every screen inside one persistent shell.
        self.shell = AppShell()
        self.build_shell()
        
        self.shell.sidebar.player_card.set_name(
            self.app_settings.value("display_name", "Ascender", type=str)
        )

        self._last_known_level = self.xp_manager.get_level()

        # ── Anonymous analytics (consent-gated, enabled by default) ──
        # Initialised last so all other components exist before any
        # telemetry call. Every call is non-blocking; failures are
        # silently swallowed so analytics never affect normal use.
        self._init_telemetry()

        # Expose the controller on the QApplication so the Settings page
        # can find it when the analytics toggle changes.
        app = QApplication.instance()
        if app is not None:
            app._ascend_controller = self

    def build_shell(self):
        """Register the existing screens as pages of the application shell."""
        self.shell.add_page(
            "dashboard",
            "Dashboard",
            "fa5s.home",
            self.dashboard,
            self.dashboard.header_actions(),
        )
        self.shell.add_page(
            "planner",
            "Planner",
            "fa5s.calendar-alt",
            self.tomorrow_planner,
            self.tomorrow_planner.header_actions(),
        )
        self.shell.add_page(
            "insights",
            "Insights",
            "fa5s.chart-bar",
            self.analytics_window,
            self.analytics_window.header_actions(),
        )
        self.shell.add_page(
            "history",
            "History",
            "fa5s.history",
            self.history_window,
        )
        self.shell.add_page(
            "progress",
            "Player Progress",
            "fa5s.user-astronaut",
            self.player_progress_page,
        )
        self.shell.add_page(
            "settings",
            "Settings",
            "fa5s.cog",
            self.settings_page,
        )

        self.shell.page_changed.connect(self.handle_page_changed)

    def refresh_sidebar_progress(self):
        """Push already-calculated XP values into the sidebar summary."""
        total_xp = self.xp_manager.get_total_xp()
        level = self.xp_manager.get_level()
        xp_into_level = total_xp % XP_PER_LEVEL
        self.shell.sidebar.player_card.set_progress(
            level,
            xp_into_level,
            XP_PER_LEVEL,
            total_xp,
        )

        if hasattr(self, "_last_known_level") and self._last_known_level is not None:
            if level > self._last_known_level:
                self.show_level_up_toast(level)
        self._last_known_level = level

    def show_level_up_toast(self, new_level):
        """LEVEL-UP-01: Display non-blocking toast overlay on genuine level transition."""
        from UI.components.toast_notification import ToastNotification
        ToastNotification.show_toast(
            self.shell,
            f"LEVEL {new_level} UNLOCKED!",
            f"Outstanding focus! You reached Level {new_level}.",
            icon_str="🚀",
        )

    def handle_page_changed(self, page_key):
        """Refresh a page's real data as it becomes visible."""
        if page_key == "dashboard":
            self.dashboard.load_today_activities()
        elif page_key == "planner":
            self.tomorrow_planner.load_activities()
            self._track("planner_used")
        elif page_key == "insights":
            self.analytics_window.refresh()
            self._track("insights_viewed")
        elif page_key == "history":
            self.history_window.load_history()
        elif page_key == "progress":
            self.player_progress_page.refresh()

        self.refresh_sidebar_progress()

    def handle_profile_changed(self, name):
        self.shell.sidebar.player_card.set_name(name)

    def handle_theme_changed(self, theme):
        ThemeManager.set_theme(theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(ThemeManager.app_stylesheet())
        # Reapply the shared stylesheet to pages that own a local stylesheet.
        self.shell.setStyleSheet(ThemeManager.app_stylesheet())
        self.shell.sidebar.refresh_theme()
        self.dashboard.setStyleSheet(ThemeManager.dashboard_stylesheet())
        self.dashboard.refresh_semantic_icons()
        self.analytics_window.setStyleSheet(ThemeManager.app_stylesheet())
        self.history_window.setStyleSheet(ThemeManager.app_stylesheet())
        self.player_progress_page.setStyleSheet(ThemeManager.app_stylesheet())
        self.settings_page.setStyleSheet(ThemeManager.app_stylesheet())
        self.tomorrow_planner.setStyleSheet(ThemeManager.app_stylesheet())

    def handle_daily_goal_changed(self):
        """Keep goal-dependent screens correct after a settings change."""
        self.dashboard.update_daily_goal_label()
        self.dashboard.update_progress_summary()
        self.notify_activity_data_changed()

    def show_dashboard(self):
        # Show the shell on the dashboard page.
        self.shell.show_page("dashboard")
        self.refresh_sidebar_progress()
        self.shell.show()

    def show_tomorrow_planner(self):
        self.shell.show_page("planner")

    def show_history(self):
        self.shell.show_page("history")

    def show_analytics(self):
        self.shell.show_page("insights")

    def show_player_progress(self):
        self.shell.show_page("progress")

    def show_settings(self):
        self.shell.show_page("settings")

    def notify_activity_data_changed(self):
        # Refresh open screens immediately after a persisted activity change.
        self.refresh_sidebar_progress()

        current_page = self.shell.current_page_key()
        if current_page == "insights":
            self.analytics_window.refresh()
        elif current_page == "progress":
            self.player_progress_page.refresh()
        elif current_page == "history":
            self.history_window.load_history()

    def _init_telemetry(self):
        """Initialise the anonymous analytics client.

        Analytics is enabled by default for fresh installations and can
        be disabled at any time in Settings. No personal data or task
        content is ever collected. All operations are non-blocking;
        failures are silently swallowed.
        """
        try:
            self.telemetry = AnalyticsClient(self.app_settings)

            # Connect to session signals for session_started / session_completed
            self.dashboard.session_engine.session_started.connect(
                lambda _: self._track("session_started")
            )
            self.dashboard.session_engine.session_completed.connect(
                lambda _: self._track("session_completed")
            )

            # Connect to dashboard signals for task and goal events
            self.dashboard.task_created.connect(lambda: self._track("task_created"))
            self.dashboard.task_completed.connect(lambda: self._track("task_completed"))
            self.dashboard.daily_goal_completed.connect(
                lambda: self._track("daily_goal_completed")
            )
            self.dashboard.xp_changed.connect(lambda: self._track("xp_changed"))

            # Track first_launch or app_launched (consent-gated)
            self.telemetry.track_first_launch_or_app_launched()

            # Detect version updates (APP_VERSION comes from Modules.version,
            # the single authoritative source)
            previous_version = self.app_settings.value(
                "telemetry/last_known_version", "", type=str
            )
            if previous_version and previous_version != APP_VERSION:
                self._track("app_version_updated")
            self.app_settings.setValue("telemetry/last_known_version", APP_VERSION)
            self.app_settings.sync()

            # Start periodic flush (every 5 minutes)
            app = QApplication.instance()
            if app is not None:
                self.telemetry.start_flush_timer()
                app.aboutToQuit.connect(self._flush_telemetry_on_shutdown)

        except Exception:
            # Analytics failure must never affect the application.
            self.telemetry = None

    def _track(self, event_name):
        """Queue one analytics event. Non-blocking; failures are silent."""
        try:
            if self.telemetry is not None:
                self.telemetry.track(event_name)
        except Exception:
            pass

    def _flush_telemetry_on_shutdown(self):
        """Attempt a final flush when the app is about to quit."""
        try:
            if self.telemetry is not None:
                self.telemetry.flush()
        except Exception:
            pass

    def close_database(self):
        # Close the shared SQLite connection when the app exits.
        self.database.close()
