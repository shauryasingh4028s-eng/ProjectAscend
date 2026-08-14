from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CompletionScreen(QWidget):
    view_history_requested = Signal()

    def __init__(
        self,
        study_minutes,
        completed_tasks,
        total_tasks,
        daily_goal,
        total_xp=0,
        level=1,
        achievements=None,
    ):
        super().__init__()

        # Store the completion statistics shown on the screen.
        self.study_minutes = study_minutes
        self.completed_tasks = completed_tasks
        self.total_tasks = total_tasks
        self.daily_goal = daily_goal
        self.total_xp = total_xp
        self.level = level
        self.achievements = achievements or []

        # Configure the completion window.
        self.setWindowTitle("Project Ascend")
        self.setFixedSize(650, 650)

        # Build the polished dark interface.
        self.apply_styles()
        self.build_ui()

    def apply_styles(self):
        # Apply a dark modern style matching the Dashboard.
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
                border-radius: 16px;
            }

            QLabel {
                background-color: transparent;
                border: none;
            }

            QPushButton {
                background-color: #2f6fed;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 18px;
                font-size: 14px;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #3d7cff;
            }
        """)

    def build_ui(self):
        # Create the main vertical layout for the whole window.
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(18)

        top_section = self.create_top_section()
        statistics_card = self.create_statistics_card()
        status_label = self.create_status_label()
        button_row = self.create_button_row()

        main_layout.addLayout(top_section)
        main_layout.addWidget(statistics_card)
        main_layout.addWidget(status_label)
        main_layout.addStretch()
        main_layout.addLayout(button_row)

        self.setLayout(main_layout)

    def create_top_section(self):
        # Create the congratulation title area.
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        emoji_label = QLabel("🎉")
        emoji_label.setStyleSheet("font-size: 56px;")
        emoji_label.setFixedHeight(70)

        title_label = QLabel("Congratulations!")
        title_label.setStyleSheet("font-size: 30px; font-weight: bold;")

        subtitle_label = QLabel("You completed every activity today.")
        subtitle_label.setStyleSheet("font-size: 16px; color: #aab2c0;")

        layout.addWidget(emoji_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)

        return layout

    def create_statistics_card(self):
        # Create a rounded card with the day's final numbers.
        card = QFrame()
        card.setMinimumHeight(300)
        layout = QVBoxLayout()
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        study_time_label = QLabel(
            f"⏱ Focus Time: {self.format_minutes(self.study_minutes)}"
        )
        completed_tasks_label = QLabel(
            f"✅ Completed Tasks: "
            f"{self.completed_tasks} / {self.total_tasks}"
        )
        daily_goal_label = QLabel(f"🎯 Daily Goal: {self.daily_goal} min")
        achievement_title = QLabel("🏅 Achievements")
        achievement_title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #f4f6fb;"
        )

        achievement_text = " • ".join(self.achievements)

        if not achievement_text:
            achievement_text = "No achievements unlocked yet."
        
        achievement_label = QLabel(achievement_text)
        achievement_label.setWordWrap(True)
        achievement_label.setMaximumHeight(90)
        achievement_label.setStyleSheet(
            "font-size: 15px; color: #d7dce7;"
        )

        achievement_label.setWordWrap(True)
        achievement_label.setObjectName("achievementLabel")
        xp_label = QLabel(
            f"⭐ Total XP: {self.total_xp}"
        )

        level_label = QLabel(
            f"🏅 Level: {self.level}"
        )

        for label in (
            study_time_label,
            completed_tasks_label,
            daily_goal_label,
            xp_label,
            level_label,
            achievement_title,
            achievement_label,
        ):
            
            label.setStyleSheet("font-size: 17px; color: #f4f6fb;")
            layout.addWidget(label)

        card.setLayout(layout)

        return card

    def create_status_label(self):
        # Show whether the user reached the daily study goal.
        if self.study_minutes >= self.daily_goal:
            status_text = "🎯 Goal Achieved"
            status_color = "#38bdf8"
        else:
            status_text = "❌ Goal Missed"
            status_color = "#f87171"

        status_label = QLabel(status_text)
        status_label.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {status_color};"
        )

        return status_label

    def create_button_row(self):
        # Create the action buttons at the bottom of the window.
        layout = QHBoxLayout()
        layout.setSpacing(12)

        self.insights_button = QPushButton("📊 View Insights")
        self.insights_button.clicked.connect(self.view_history_requested.emit)

        self.continue_button = QPushButton("🚀 Continue")
        self.continue_button.clicked.connect(self.close)

        layout.addStretch()
        layout.addWidget(self.insights_button)
        layout.addWidget(self.continue_button)

        return layout

    def format_minutes(self, minutes):
        # Convert minutes into a friendly Xh Ym format.
        hours = minutes // 60
        remaining_minutes = minutes % 60

        return f"{hours}h {remaining_minutes}m"
