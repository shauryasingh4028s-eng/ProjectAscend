from datetime import date, datetime

from PySide6.QtCore import QPropertyAnimation, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Dialogs.add_activity_dialog import AddActivityDialog
from Modules.focus_mode import FocusMode
from Modules.session import SessionEngine
from Modules.date_utils import format_duration
from Modules.gamification_config import XP_PER_LEVEL, xp_into_level
from Modules.streak_manager import StreakManager
from UI.components.dashboard_widgets import (
    ActionBar,
    ActivityCard,
    ActivitySection,
    FocusCard,
    HeroCard,
    PlayerCard,
    ProgressCard,
)
from UI.theme.design_system import ButtonFactory, IconFactory, ThemeManager

try:
    from Modules.xp_manager import XPManager
except ImportError:
    XPManager = None


class DashboardV2(QWidget):
    def __init__(self, database, app_controller=None):
        super().__init__()

        self.database = database
        self.app_controller = app_controller
        self.selected_date = date.today().isoformat()
        self.activities = []
        self.selected_activity_id = None
        self.focus_mode = None
        self.progress_animation = None
        self.xp_animation = None

        self.icon_factory = IconFactory(self)
        self.button_factory = ButtonFactory(self.icon_factory)

        self.session_engine = SessionEngine(self.database)
        self.connect_session_signals()

        self.setWindowTitle("Project Ascend")

        self.apply_styles()
        self.build_ui()
        self.create_shortcuts()
        self.load_today_activities()

    def header_actions(self):
        """Return the buttons the application shell shows in the page header."""
        return (self.add_today_button, self.settings_button)

    def connect_session_signals(self):
        self.session_engine.timer_updated.connect(self.update_timer_label)
        self.session_engine.session_started.connect(self.show_current_activity)
        self.session_engine.session_paused.connect(self.show_paused_state)
        self.session_engine.session_resumed.connect(self.show_running_state)
        self.session_engine.session_completed.connect(self.finish_session)

    def apply_styles(self):
        self.setStyleSheet(ThemeManager.dashboard_stylesheet())

    def build_ui(self):
        # Build the action buttons first so the shell header can reuse them.
        action_bar = self.create_action_bar()

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(14)

        main_layout.addWidget(self.create_header())
        main_layout.addLayout(self.create_progress_cards())
        main_layout.addWidget(self.create_focus_card())
        main_layout.addWidget(self.create_activity_card(), 1)
        main_layout.addWidget(action_bar)

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)
        self.setLayout(outer_layout)

    def create_header(self):
        self.settings_button = self.button_factory.secondary("Settings", "fa5s.cog")
        self.settings_button.clicked.connect(self.open_settings_dialog)
        return HeroCard(self.settings_button, self.get_greeting())

    def create_progress_cards(self):
        layout = QHBoxLayout()
        layout.setSpacing(16)

        self.progress_card = ProgressCard(self.icon_factory)
        self.daily_goal_label = self.progress_card.daily_goal_label
        self.progress_bar = self.progress_card.progress_bar
        self.study_time_label = self.progress_card.study_time_label
        self.completed_total_label = self.progress_card.completed_total_label
        self.remaining_minutes_label = self.progress_card.remaining_minutes_label
        self.update_daily_goal_label()

        player_card = self.create_player_progress_card()

        layout.addWidget(self.progress_card, 3)
        layout.addWidget(player_card, 2)
        return layout

    def create_player_progress_card(self):
        self.player_card = PlayerCard(self.icon_factory)
        self.level_label = self.player_card.level_label
        self.current_xp_label = self.player_card.current_xp_label
        self.xp_bar = self.player_card.xp_bar
        self.current_streak_label = self.player_card.current_streak_label
        self.best_streak_label = self.player_card.best_streak_label
        return self.player_card

    def refresh_semantic_icons(self):
        """Re-render dashboard metric icons with the active theme."""
        self.progress_card.refresh_semantic_icons()
        self.player_card.refresh_semantic_icons()

    def create_focus_card(self):
        self.start_button = self.button_factory.primary("Start", "fa5s.play")
        self.start_button.clicked.connect(self.start_selected_activity)

        self.pause_button = self.button_factory.secondary("Pause", "fa5s.pause")
        self.pause_button.clicked.connect(self.pause_or_resume_session)
        self.pause_button.setEnabled(False)

        self.complete_button = self.button_factory.success("Complete", "fa5s.check")
        self.complete_button.clicked.connect(self.complete_current_activity)
        self.complete_button.setEnabled(False)

        focus_card = FocusCard(
            self.start_button,
            self.pause_button,
            self.complete_button,
        )
        self.current_activity_label = focus_card.current_activity_label
        self.timer_label = focus_card.timer_label
        return focus_card

    def create_activity_card(self):
        self.activity_section = ActivitySection()
        self.activity_section.activity_selected.connect(self.select_activity_by_id)
        self.activity_section.activity_double_clicked.connect(self.start_activity_by_id)
        self.activity_section.activity_menu_requested.connect(
            self.show_activity_menu_for_id
        )
        return self.activity_section

    def create_action_bar(self):
        self.add_today_button = self.button_factory.action(
            "Add Activity",
            "fa5s.plus",
        )
        self.add_today_button.clicked.connect(self.open_add_today_dialog)

        self.plan_tomorrow_button = self.button_factory.action(
            "Plan Tomorrow",
            "fa5s.calendar-alt",
        )
        self.plan_tomorrow_button.clicked.connect(self.open_tomorrow_planner)

        self.insights_button = self.button_factory.action("Insights", "fa5s.chart-line")
        self.insights_button.clicked.connect(self.open_insights)

        return ActionBar(
            self.add_today_button,
            self.plan_tomorrow_button,
            self.insights_button,
        )

    def create_shortcuts(self):
        pause_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        pause_shortcut.activated.connect(self.pause_or_resume_session)

        complete_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        complete_shortcut.activated.connect(self.complete_current_activity)

    def get_greeting(self):
        current_hour = datetime.now().hour

        if current_hour < 12:
            return "Good Morning"
        if current_hour < 17:
            return "Good Afternoon"
        return "Good Evening"

    def load_today_activities(self):
        self.activity_section.clear_cards()
        self.activities = self.database.get_activities_for_date(self.selected_date)

        if not self.activities:
            self.activity_section.add_empty_state(
                "No activities planned for today. Click 'Add Activity' to begin."
            )
            self.update_progress_summary()
            self.update_player_progress()
            return

        for activity in self.activities:
            overflow_button = self.button_factory.icon_button("fa5s.ellipsis-h")
            card = ActivityCard(activity, self.icon_factory, overflow_button)
            self.activity_section.add_activity_card(activity.id, card)

        self.update_progress_summary()
        self.update_player_progress()

    def select_activity_by_id(self, activity_id):
        self.selected_activity_id = activity_id

    def start_activity_by_id(self, activity_id):
        self.selected_activity_id = activity_id
        self.activity_section.select_activity(activity_id)
        self.start_selected_activity()

    def get_activity_list_text(self, activity):
        status = "Completed" if activity.completed else "Planned"
        return (
            f"{status} | "
            f"{activity.activity_type} | "
            f"{activity.name} | "
            f"Estimated: {activity.estimated_minutes} min | "
            f"Actual: {activity.actual_minutes} min"
        )

    def update_progress_summary(self):
        daily_goal = self.database.get_daily_goal()
        total_activities = len(self.activities)
        completed_activities = 0
        study_minutes = 0

        for activity in self.activities:
            if activity.completed:
                completed_activities += 1
                study_minutes += activity.actual_minutes

        remaining_minutes = daily_goal - study_minutes

        if remaining_minutes < 0:
            remaining_minutes = 0

        if daily_goal <= 0:
            progress_percent = 0
        else:
            progress_percent = int((study_minutes / daily_goal) * 100)

        if progress_percent > 100:
            progress_percent = 100

        hours = study_minutes // 60
        minutes = study_minutes % 60

        self.animate_progress_bar(self.progress_bar, progress_percent)
        self.study_time_label.setText(f"{hours}h {minutes}m")
        self.completed_total_label.setText(f"{completed_activities} / {total_activities}")
        self.remaining_minutes_label.setText(format_duration(remaining_minutes))

    def update_daily_goal_label(self):
        daily_goal = self.database.get_daily_goal()
        hours = daily_goal // 60
        minutes = daily_goal % 60

        if minutes == 0:
            goal_text = f"{hours} hours"
        else:
            goal_text = f"{hours}h {minutes}m"

        self.daily_goal_label.setText(f"Goal: {daily_goal} min / {goal_text}")

    def update_player_progress(self):
        level, current_xp = self.get_xp_summary()

        streak_manager = StreakManager(self.database)
        current_streak = streak_manager.get_current_streak()
        best_streak = streak_manager.get_longest_streak()

        self.level_label.setText(f"Level {level}")
        self.current_xp_label.setText(f"{current_xp} XP")
        self.current_streak_label.setText(f"{current_streak} days")
        self.best_streak_label.setText(f"{best_streak} days")
        self.animate_xp_bar(min(xp_into_level(current_xp), XP_PER_LEVEL))

    def get_xp_summary(self):
        if XPManager is None:
            return 1, 0

        xp_manager = XPManager(self.database)
        level = self.call_first_available_method(
            xp_manager,
            ["get_level", "get_current_level"],
            1,
        )
        current_xp = self.call_first_available_method(
            xp_manager,
            ["get_current_xp", "get_total_xp", "get_xp"],
            0,
        )
        return level, current_xp

    def call_first_available_method(self, object_instance, method_names, default):
        for method_name in method_names:
            if hasattr(object_instance, method_name):
                method = getattr(object_instance, method_name)
                return method()
        return default

    def get_selected_activity(self):
        if self.selected_activity_id is None:
            return None

        for activity in self.activities:
            if activity.id == self.selected_activity_id:
                return activity
        return None

    def start_selected_activity(self):
        activity = self.get_selected_activity()

        if activity is None:
            self.current_activity_label.setText("Current Activity: Select an activity first")
            return

        if activity.completed:
            self.current_activity_label.setText(
                "Current Activity: This activity is already completed"
            )
            return

        if self.session_engine.current_activity is not None:
            self.current_activity_label.setText("Current Activity: A session is already running")
            self.open_focus_mode(self.session_engine.current_activity)
            return

        self.session_engine.start(activity)
        self.open_focus_mode(activity)

    def open_focus_mode(self, activity):
        try:
            self.focus_mode = FocusMode(
                activity=activity,
                session_engine=self.session_engine,
                dashboard=self,
            )
        except TypeError:
            self.focus_mode = FocusMode(activity, self.session_engine)

        self.focus_mode.show()

    def pause_or_resume_session(self):
        if self.session_engine.current_activity is None:
            return

        if self.session_engine.is_running:
            self.session_engine.pause()
        else:
            self.session_engine.resume()

    def complete_current_activity(self):
        if self.session_engine.current_activity is None:
            return

        self.session_engine.complete()

    def open_add_today_dialog(self):
        dialog = AddActivityDialog(self.database, self.selected_date)

        if dialog.exec():
            self.load_today_activities()
            self.current_activity_label.setText("Current Activity: Today's task added")

    def open_settings_dialog(self):
        # Prefer the shell's Settings page so there is one place to edit
        # preferences. The dialog remains for standalone use.
        if self.app_controller is not None and hasattr(
            self.app_controller, "show_settings"
        ):
            self.app_controller.show_settings()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setModal(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Daily Goal (minutes)")
        title.setObjectName("SectionTitle")

        daily_goal_input = QSpinBox()
        daily_goal_input.setMinimum(30)
        daily_goal_input.setMaximum(1440)
        daily_goal_input.setValue(self.database.get_daily_goal())

        button_layout = QHBoxLayout()
        save_button = self.button_factory.primary("Save", "fa5s.save")
        cancel_button = self.button_factory.secondary("Cancel", "fa5s.times")

        save_button.clicked.connect(
            lambda: self.save_daily_goal(dialog, daily_goal_input.value())
        )
        cancel_button.clicked.connect(dialog.reject)

        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        layout.addWidget(title)
        layout.addWidget(daily_goal_input)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        dialog.exec()

    def save_daily_goal(self, dialog, value):
        self.database.set_daily_goal(value)
        self.update_daily_goal_label()
        self.update_progress_summary()
        dialog.accept()

    def open_history(self):
        if self.app_controller is not None:
            self.app_controller.show_history()

    def open_insights(self):
        if self.app_controller is not None:
            self.app_controller.show_analytics()

    def open_tomorrow_planner(self):
        if self.app_controller is not None:
            self.app_controller.show_tomorrow_planner()

    def show_activity_menu(self, position):
        return

    def show_activity_menu_for_id(self, activity_id, global_position):
        self.selected_activity_id = activity_id
        self.activity_section.select_activity(activity_id)

        menu = QMenu(self)
        edit_action = menu.addAction("Edit Activity")
        delete_action = menu.addAction("Delete Activity")
        selected_action = menu.exec(global_position)

        if selected_action == edit_action:
            self.edit_selected_activity()
        elif selected_action == delete_action:
            self.delete_selected_activity()

    def edit_selected_activity(self):
        activity = self.get_selected_activity()

        if activity is None:
            return

        used_fallback_dialog = False

        try:
            dialog = AddActivityDialog(self.database, self.selected_date, activity)
        except TypeError:
            used_fallback_dialog = True
            dialog = AddActivityDialog(self.database, self.selected_date)
            self.prefill_activity_dialog(dialog, activity)

        if not dialog.exec():
            return

        if used_fallback_dialog and activity.id is not None:
            self.database.delete_activity(activity.id)

        self.load_today_activities()
        self.current_activity_label.setText(f"Current Activity: Updated {activity.name}")

    def prefill_activity_dialog(self, dialog, activity):
        if hasattr(dialog, "activity_type"):
            index = dialog.activity_type.findText(activity.activity_type)

            if index >= 0:
                dialog.activity_type.setCurrentIndex(index)

        if hasattr(dialog, "activity_name"):
            dialog.activity_name.setText(activity.name)

        if hasattr(dialog, "estimated_time"):
            dialog.estimated_time.setValue(activity.estimated_minutes)

    def delete_selected_activity(self):
        activity = self.get_selected_activity()

        if activity is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete Activity",
            f'Delete "{activity.name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.database.delete_activity(activity.id)
        self.load_today_activities()
        self.current_activity_label.setText(f"Current Activity: Deleted {activity.name}")

    def finish_session(self, activity):
        self.current_activity_label.setText(f"Completed: {activity.name}. Excellent work.")
        self.reset_session_buttons()

        progression_update = None
        if self.app_controller is not None and hasattr(
            self.app_controller,
            "progression_service",
        ):
            progression_update = (
                self.app_controller.progression_service.process_activity_completion(
                    activity.id,
                    activity.date,
                )
            )
            self.app_controller.notify_activity_data_changed()
            self.app_controller.handle_progression_update(progression_update)
        elif self.app_controller is not None:
            self.app_controller.xp_manager.award_activity_completion(activity.id)
            self.app_controller.notify_activity_data_changed()
        elif XPManager is not None:
            XPManager(self.database).award_activity_completion(activity.id)

        self.load_today_activities()

        # Preserve the existing all-activities-complete acknowledgement when
        # no stronger progression reward already recognizes this action.
        if self.all_today_activities_complete() and not (
            progression_update is not None
            and progression_update.has_celebration
        ):
            QMessageBox.information(
                self,
                "Congratulations!",
                "You completed every activity today.\n\nExcellent work.",
            )

    def all_today_activities_complete(self):
        if not self.activities:
            return False

        for activity in self.activities:
            if not activity.completed:
                return False
        return True

    def reset_session_buttons(self):
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        self.pause_button.setText("Pause")

    def update_timer_label(self, seconds):
        formatted_time = self.session_engine.format_time(seconds)
        self.timer_label.setText(formatted_time)

    def show_current_activity(self, activity):
        self.current_activity_label.setText(f"Current Activity: {activity.name}")
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.complete_button.setEnabled(True)
        self.pause_button.setText("Pause")

    def show_paused_state(self):
        self.pause_button.setText("Resume")
        self.current_activity_label.setText("Current Activity: Paused")

    def show_running_state(self):
        self.pause_button.setText("Pause")

        if self.session_engine.current_activity is not None:
            self.current_activity_label.setText(
                f"Current Activity: {self.session_engine.current_activity.name}"
            )

    def animate_progress_bar(self, progress_bar, target_value):
        self.progress_animation = QPropertyAnimation(progress_bar, b"value")
        self.progress_animation.setDuration(220)
        self.progress_animation.setStartValue(progress_bar.value())
        self.progress_animation.setEndValue(target_value)
        self.progress_animation.start()

    def animate_xp_bar(self, target_value):
        self.xp_animation = QPropertyAnimation(self.xp_bar, b"value")
        self.xp_animation.setDuration(220)
        self.xp_animation.setStartValue(self.xp_bar.value())
        self.xp_animation.setEndValue(target_value)
        self.xp_animation.start()


Dashboard = DashboardV2
