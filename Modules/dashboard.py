from Modules.completion_screen import CompletionScreen
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Dialogs.add_activity_dialog import AddActivityDialog
from Modules.focus_mode import FocusMode
from Modules.session import SessionEngine
from Modules.date_utils import format_duration


class Dashboard(QWidget):
    def __init__(self, database, app_controller=None):
        super().__init__()

        # Store shared app services used by the dashboard.
        self.database = database
        self.app_controller = app_controller

        # Store the currently loaded date and activity list.
        self.selected_date = date.today().isoformat()
        self.activities = []

        # Store the Focus Mode window while it is open.
        self.focus_mode = None
        self.completion_screen = None

        # Create one SessionEngine for the dashboard and Focus Mode to share.
        self.session_engine = SessionEngine(self.database)
        self.connect_session_signals()

        # Configure the dashboard window.
        self.setWindowTitle("Project Ascend Dashboard")
        self.resize(900, 680)

        # Build and prepare the user interface.
        self.apply_styles()
        self.build_ui()
        self.create_shortcuts()

        # Load today's activities when the dashboard opens.
        self.load_today_activities()

    def connect_session_signals(self):
        # Connect SessionEngine signals to dashboard update methods.
        self.session_engine.timer_updated.connect(self.update_timer_label)
        self.session_engine.session_started.connect(self.show_current_activity)
        self.session_engine.session_paused.connect(self.show_paused_state)
        self.session_engine.session_resumed.connect(self.show_running_state)
        self.session_engine.session_completed.connect(self.finish_session)

    def apply_styles(self):
        # Apply the existing modern dark dashboard theme.
        self.setStyleSheet("""
            QWidget {
                background-color: #111318;
                color: #f4f6fb;
                font-family: Segoe UI;
                font-size: 14px;
            }

            QFrame {
                background-color: #1a1d24;
                border: 1px solid #2a2f3a;
                border-radius: 12px;
            }

            QLabel {
                background-color: transparent;
                border: none;
            }

            QListWidget {
                background-color: #151820;
                border: 1px solid #2a2f3a;
                border-radius: 10px;
                padding: 8px;
            }

            QListWidget::item {
                padding: 10px;
                border-radius: 8px;
            }

            QListWidget::item:selected {
                background-color: #2f6fed;
                color: white;
            }

            QPushButton {
                background-color: #2f6fed;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #3d7cff;
            }

            QPushButton:disabled {
                background-color: #30343d;
                color: #8c93a3;
            }

            QProgressBar {
                background-color: #151820;
                border: 1px solid #2a2f3a;
                border-radius: 8px;
                height: 18px;
                text-align: center;
                color: #f4f6fb;
                font-weight: 600;
            }

            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 8px;
            }

            QMenu {
                background-color: #1a1d24;
                border: 1px solid #2a2f3a;
                color: #f4f6fb;
                padding: 6px;
            }

            QMenu::item {
                padding: 8px 18px;
                border-radius: 6px;
            }

            QMenu::item:selected {
                background-color: #2f6fed;
            }

            QDialog {
                background-color: #111318;
                color: #f4f6fb;
                font-family: Segoe UI;
                font-size: 14px;
            }

            QSpinBox {
                background-color: #151820;
                color: #f4f6fb;
                border: 1px solid #2a2f3a;
                border-radius: 8px;
                padding: 8px;
            }
                           
            QPushButton#gearButton {
                background-color: transparent;
                border: none;
                font-size: 22px;
                font-weight: bold;
                color: white;
            }

            QPushButton#gearButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 21px;
            }              
        """)

    def build_ui(self):
        # Build the main dashboard sections.
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        main_layout.addWidget(self.create_header_section())
        main_layout.addWidget(self.create_session_section())
        main_layout.addWidget(self.create_progress_section())
        main_layout.addWidget(self.create_activities_section())

        self.setLayout(main_layout)

    def create_header_section(self):
        # Create the header section with app name and date.
        section = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)

        title = QLabel("Project Ascend")
        title.setStyleSheet("font-size: 28px; font-weight: bold;")

        subtitle = QLabel(f"Dashboard for {self.selected_date}")
        subtitle.setStyleSheet("color: #aab2c0;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        section.setLayout(layout)

        return section

    def create_session_section(self):
        # Create the current session section with timer and controls.
        section = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        section_title = QLabel("Current Session")
        section_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.current_activity_label = QLabel("Current Activity: Ready")
        self.current_activity_label.setStyleSheet("color: #d7dce7;")

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("font-size: 48px; font-weight: bold;")

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_selected_activity)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_or_resume_session)
        self.pause_button.setEnabled(False)

        self.complete_button = QPushButton("Complete")
        self.complete_button.clicked.connect(self.complete_current_activity)
        self.complete_button.setEnabled(False)

        self.add_today_button = QPushButton("Add Today's Task")
        self.add_today_button.clicked.connect(self.open_add_today_dialog)

        self.plan_tomorrow_button = QPushButton("Plan Tomorrow")
        self.plan_tomorrow_button.clicked.connect(self.open_tomorrow_planner)

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("gearButton")
        self.settings_button.setFixedSize(42, 42)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self.open_settings_dialog)

        self.settings_button.setFixedSize(40, 40)
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self.open_settings_dialog)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.complete_button)

        button_layout.addWidget(self.add_today_button)
        button_layout.addWidget(self.plan_tomorrow_button)

        button_layout.addStretch()

        button_layout.addWidget(self.settings_button)

        layout.addWidget(section_title)
        layout.addWidget(self.current_activity_label)
        layout.addWidget(self.timer_label)
        layout.addLayout(button_layout)
        section.setLayout(layout)

        return section

    def create_progress_section(self):
        # Create the progress section for today's goal tracking.
        section = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        section_title = QLabel("Today's Progress")
        section_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.daily_goal_label = QLabel()
        self.daily_goal_label.setStyleSheet("color: #aab2c0;")
        self.update_daily_goal_label()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        first_stats_layout = QHBoxLayout()
        first_stats_layout.setSpacing(12)

        self.study_time_label = QLabel("Focus Time: 0 min")
        self.completed_total_label = QLabel("Completed Activities: 0 / 0")

        self.study_time_label.setStyleSheet("color: #d7dce7;")
        self.completed_total_label.setStyleSheet("color: #d7dce7;")

        first_stats_layout.addWidget(self.study_time_label)
        first_stats_layout.addWidget(self.completed_total_label)
        first_stats_layout.addStretch()

        second_stats_layout = QHBoxLayout()
        second_stats_layout.setSpacing(12)

        daily_goal = self.database.get_daily_goal()
        self.remaining_minutes_label = QLabel(
            f"Remaining Time: {format_duration(daily_goal)}"
        )

        self.current_streak_label = QLabel()
        self.best_streak_label = QLabel()

        self.remaining_minutes_label.setStyleSheet("color: #d7dce7;")

        second_stats_layout.addWidget(self.remaining_minutes_label)
        second_stats_layout.addWidget(self.current_streak_label)
        second_stats_layout.addWidget(self.best_streak_label)
        second_stats_layout.addStretch()

        layout.addWidget(section_title)
        layout.addWidget(self.daily_goal_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(first_stats_layout)
        layout.addLayout(second_stats_layout)
        section.setLayout(layout)

        return section

    def create_activities_section(self):
        # Create the QListWidget section for today's activities.
        section = QFrame()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        section_title = QLabel("Today's Activities")
        section_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.activity_list = QListWidget()
        self.activity_list.itemDoubleClicked.connect(
            lambda _: self.start_selected_activity()
        )
        self.activity_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.activity_list.customContextMenuRequested.connect(
            self.show_activity_menu
        )

        layout.addWidget(section_title)
        layout.addWidget(self.activity_list)
        section.setLayout(layout)

        return section

    def create_shortcuts(self):
        # Create keyboard shortcuts for common session actions.
        pause_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        pause_shortcut.activated.connect(self.pause_or_resume_session)

        complete_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        complete_shortcut.activated.connect(self.complete_current_activity)

    def load_today_activities(self):
        # Load today's activities from SQLite and refresh the list widget.
        self.activity_list.clear()
        self.activities = self.database.get_activities_for_date(
            self.selected_date
        )

        if not self.activities:
            empty_item = QListWidgetItem(
                "No activities planned for today. "
                "Click 'Add Today's Task' to begin."
            )
            empty_item.setFlags(Qt.NoItemFlags)
            self.activity_list.addItem(empty_item)
            self.update_progress_summary()
            return

        for activity in self.activities:
            item = QListWidgetItem(self.get_activity_list_text(activity))
            item.setData(Qt.UserRole, activity.id)
            self.activity_list.addItem(item)

        self.update_progress_summary()

    def get_activity_list_text(self, activity):
        # Format one activity row with status and time details.
        status = "✅ Completed" if activity.completed else "⬜ Planned"

        return (
            f"{status} | "
            f"{activity.activity_type} | "
            f"{activity.name} | "
            f"Estimated: {activity.estimated_minutes} min | "
            f"Actual: {activity.actual_minutes} min"
        )

    def update_progress_summary(self):
        # Calculate goal progress from completed activity time.
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

        self.progress_bar.setValue(progress_percent)
        hours = study_minutes // 60
        minutes = study_minutes % 60

        self.study_time_label.setText(f"Focus Time: {hours}h {minutes}m")
        self.completed_total_label.setText(
            f"Completed Activities: {completed_activities} / "
            f"{total_activities}"
        )
        self.remaining_minutes_label.setText(
            f"Remaining Time: {format_duration(remaining_minutes)}"
        )

        current_streak = self.app_controller.streak_manager.get_current_streak()
        best_streak = self.app_controller.streak_manager.get_longest_streak()
        
        self.current_streak_label.setText(
            f"🔥 Current Streak: {current_streak}"
        )
        
        self.best_streak_label.setText(
            f"🏆 Best Streak: {best_streak}"
        )        

    def update_daily_goal_label(self):
        # Refresh the daily goal label from the permanent database setting.
        daily_goal = self.database.get_daily_goal()
        hours = daily_goal // 60
        minutes = daily_goal % 60

        if minutes == 0:
            goal_text = f"{hours} hours"
        else:
            goal_text = f"{hours}h {minutes}m"

        self.daily_goal_label.setText(
            f"Daily Goal: {daily_goal} min / {goal_text}"
        )

    def get_selected_activity(self):
        # Return the activity object selected in the QListWidget.
        selected_items = self.activity_list.selectedItems()

        if not selected_items:
            return None

        activity_id = selected_items[0].data(Qt.UserRole)

        if activity_id is None:
            return None

        for activity in self.activities:
            if activity.id == activity_id:
                return activity

        return None

    def start_selected_activity(self):
        # Start the selected activity and open Focus Mode.
        activity = self.get_selected_activity()

        if activity is None:
            self.current_activity_label.setText(
                "Current Activity: Select an activity first"
            )
            return

        if activity.completed:
            self.current_activity_label.setText(
                "Current Activity: This activity is already completed"
            )
            return

        if self.session_engine.current_activity is not None:
            self.current_activity_label.setText(
                "Current Activity: A session is already running"
            )
            self.open_focus_mode(self.session_engine.current_activity)
            return

        self.session_engine.start(activity)
        self.open_focus_mode(activity)

    def open_focus_mode(self, activity):
        # Open Focus Mode using the selected activity and existing engine.
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
        # Pause or resume the active session.
        if self.session_engine.current_activity is None:
            return

        if self.session_engine.is_running:
            self.session_engine.pause()
        else:
            self.session_engine.resume()

    def complete_current_activity(self):
        # Complete the active session through SessionEngine.
        if self.session_engine.current_activity is None:
            return

        self.session_engine.complete()

    def open_add_today_dialog(self):
        # Open AddActivityDialog for today's date.
        dialog = AddActivityDialog(self.database, self.selected_date)

        if dialog.exec():
            self.load_today_activities()
            self.current_activity_label.setText(
                "Current Activity: Today's task added"
            )

    def open_settings_dialog(self):
        # Open a modal dialog for editing the permanent daily goal.
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setModal(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Daily Goal (minutes)")
        title.setStyleSheet("font-weight: bold;")

        daily_goal_input = QSpinBox()
        daily_goal_input.setMinimum(30)
        daily_goal_input.setMaximum(1440)
        daily_goal_input.setValue(self.database.get_daily_goal())

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")

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
        # Save the daily goal and refresh progress immediately.
        self.database.set_daily_goal(value)
        self.update_daily_goal_label()
        self.update_progress_summary()
        dialog.accept()

    def open_history(self):
        # Ask AppController to show the History window.
        if self.app_controller is not None:
            self.app_controller.show_history()

    def show_activity_menu(self, position):
        # Show edit/delete actions for the activity under the cursor.
        item = self.activity_list.itemAt(position)

        if item is None or item.data(Qt.UserRole) is None:
            return

        self.activity_list.setCurrentItem(item)

        menu = QMenu(self)
        edit_action = menu.addAction("✏ Edit Activity")
        delete_action = menu.addAction("🗑 Delete Activity")

        selected_action = menu.exec(self.activity_list.mapToGlobal(position))

        if selected_action == edit_action:
            self.edit_selected_activity()
        elif selected_action == delete_action:
            self.delete_selected_activity()

    def edit_selected_activity(self):
        # Edit the selected activity using AddActivityDialog.
        activity = self.get_selected_activity()

        if activity is None:
            return

        used_fallback_dialog = False

        try:
            dialog = AddActivityDialog(
                self.database,
                self.selected_date,
                activity,
            )
        except TypeError:
            used_fallback_dialog = True
            dialog = AddActivityDialog(self.database, self.selected_date)
            self.prefill_activity_dialog(dialog, activity)

        if not dialog.exec():
            return

        if used_fallback_dialog and activity.id is not None:
            self.database.delete_activity(activity.id)

        self.load_today_activities()
        self.current_activity_label.setText(
            f"Current Activity: Updated {activity.name}"
        )

    def prefill_activity_dialog(self, dialog, activity):
        # Fill AddActivityDialog fields when it does not support edit mode.
        if hasattr(dialog, "activity_type"):
            index = dialog.activity_type.findText(activity.activity_type)

            if index >= 0:
                dialog.activity_type.setCurrentIndex(index)

        if hasattr(dialog, "activity_name"):
            dialog.activity_name.setText(activity.name)

        if hasattr(dialog, "estimated_time"):
            dialog.estimated_time.setValue(activity.estimated_minutes)

    def delete_selected_activity(self):
        # Confirm and delete the selected activity from SQLite.
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
        self.current_activity_label.setText(
            f"Current Activity: Deleted {activity.name}"
        )

    def open_tomorrow_planner(self):
        # Ask AppController to show the Tomorrow Planner.
        if self.app_controller is not None:
            self.app_controller.show_tomorrow_planner()

    def finish_session(self, activity):
        # Refresh dashboard state after SessionEngine completes an activity.
        self.current_activity_label.setText(
            f"Completed: {activity.name}. Excellent work."
        )
        self.reset_session_buttons()
        self.load_today_activities()

        self.app_controller.xp_manager.award_activity_completion()

        if self.all_today_activities_complete():
            self.app_controller.xp_manager.award_daily_goal()

            completed_tasks = sum(
                1 for activity in self.activities if activity.completed
            )

        study_minutes = sum(
            activity.actual_minutes
            for activity in self.activities
            if activity.completed
        )

        self.completion_screen = CompletionScreen(
            study_minutes=study_minutes,
            completed_tasks=completed_tasks,
            total_tasks=len(self.activities),
            daily_goal=self.database.get_daily_goal(),
            total_xp=self.app_controller.xp_manager.get_total_xp(),
            level=self.app_controller.xp_manager.get_level(),
            achievements=self.app_controller.achievement_manager.get_unlocked(),    
        )

        self.completion_screen.view_history_requested.connect(
            self.open_history
        )

        self.completion_screen.show()

    def all_today_activities_complete(self):
        # Return True only when every loaded activity is completed.
        if not self.activities:
            return False

        for activity in self.activities:
            if not activity.completed:
                return False

        return True

    def reset_session_buttons(self):
        # Reset dashboard session buttons to their default state.
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        self.pause_button.setText("Pause")

    def update_timer_label(self, seconds):
        # Keep the dashboard timer synchronized with SessionEngine.
        formatted_time = self.session_engine.format_time(seconds)
        self.timer_label.setText(formatted_time)

    def show_current_activity(self, activity):
        # Show current activity and enable active-session controls.
        self.current_activity_label.setText(
            f"Current Activity: {activity.name}"
        )
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.complete_button.setEnabled(True)
        self.pause_button.setText("Pause")

    def show_paused_state(self):
        # Update dashboard controls when the session is paused.
        self.pause_button.setText("Resume")
        self.current_activity_label.setText("Current Activity: Paused")

    def show_running_state(self):
        # Update dashboard controls when the session resumes.
        self.pause_button.setText("Pause")

        if self.session_engine.current_activity is not None:
            self.current_activity_label.setText(
                f"Current Activity: "
                f"{self.session_engine.current_activity.name}"
            )
