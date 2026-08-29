"""Achievement Library Modal Dialog."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Modules.achievement_manager import ACHIEVEMENT_DEFINITIONS
from UI.theme.design_system import Colors, Radius, Spacing, Typography
from UI.theme.motion_utils import is_reduced_motion_enabled


class AchievementCardWidget(QFrame):
    """Tile representing a single catalog achievement with locked/unlocked state."""

    def __init__(self, achievement_info, unlock_record=None):
        super().__init__()
        self.achievement_id = achievement_info["id"]
        self.is_unlocked = unlock_record is not None

        self.setObjectName("InsightItem")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if self.is_unlocked:
            self.setProperty("selected", "true")
        else:
            self.setProperty("locked", "true")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.MD + 2)
        layout.setSpacing(Spacing.LG)

        # Icon badge
        icon_label = QLabel(achievement_info["icon"])
        icon_label.setObjectName("Badge" if not self.is_unlocked else "LevelBadge")
        icon_label.setFixedSize(52, 52)
        icon_label.setAlignment(Qt.AlignCenter)
        if self.is_unlocked:
            icon_label.setStyleSheet("font-size: 24px;")
        else:
            icon_label.setStyleSheet(f"background-color: {Colors.SURFACE_ELEVATED}; color: {Colors.TEXT_MUTED}; border-radius: 14px; font-size: 22px;")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        header_row = QHBoxLayout()
        header_row.setSpacing(Spacing.SM)

        name_label = QLabel(achievement_info["name"])
        name_label.setObjectName("Greeting" if self.is_unlocked else "SectionTitle")
        name_label.setStyleSheet("font-size: 15px; font-weight: 750;" if self.is_unlocked else f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_MUTED};")

        cat_badge = QLabel(achievement_info["category"])
        cat_badge.setObjectName("Badge")

        header_row.addWidget(name_label)
        header_row.addWidget(cat_badge)
        header_row.addStretch()

        desc_label = QLabel(achievement_info["description"])
        desc_label.setObjectName("MutedText")
        desc_label.setWordWrap(True)

        text_layout.addLayout(header_row)
        text_layout.addWidget(desc_label)

        if self.is_unlocked:
            unlocked_at_str = unlock_record.get("unlocked_at", "") if isinstance(unlock_record, dict) else (unlock_record[1] if isinstance(unlock_record, (list, tuple)) and len(unlock_record) > 1 else "")
            date_display = unlocked_at_str.split("T")[0] if "T" in unlocked_at_str else unlocked_at_str
            date_label = QLabel(f"Unlocked: {date_display}" if date_display else "Unlocked")
            date_label.setObjectName("CompletedBadge")
            text_layout.addWidget(date_label)
        else:
            locked_label = QLabel("Locked")
            locked_label.setObjectName("Badge")
            text_layout.addWidget(locked_label)

        layout.addWidget(icon_label)
        layout.addLayout(text_layout, 1)

    def enterEvent(self, event):
        super().enterEvent(event)
        if not is_reduced_motion_enabled():
            self.setProperty("hovered", "true")
            self.setStyle(self.style())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not is_reduced_motion_enabled():
            self.setProperty("hovered", "false")
            self.setStyle(self.style())


class AchievementLibraryDialog(QDialog):
    """Modal dialog displaying all catalog achievements by category."""

    def __init__(self, achievement_manager, parent=None):
        super().__init__(parent)
        self.achievement_manager = achievement_manager

        self.setWindowTitle("Achievement Library")
        self.setMinimumSize(840, 620)
        self.resize(860, 640)

        self.active_category = "All"
        self.build_ui()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        root_layout.setSpacing(Spacing.LG)

        # Header
        unlocked_rows = self.achievement_manager.database.get_unlocked_achievements()
        self.unlocked_dict = {
            r["achievement_id"] if isinstance(r, dict) else r[0]: r
            for r in unlocked_rows
        }

        total_count = len(ACHIEVEMENT_DEFINITIONS)
        unlocked_count = len(self.unlocked_dict)

        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        title = QLabel("Achievement Library")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Milestones of focus, consistency, and planning mastery.")
        subtitle.setObjectName("MutedText")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        summary_badge = QLabel(f"Unlocked: {unlocked_count} / {total_count}")
        summary_badge.setObjectName("CompletedBadge")

        header_layout.addLayout(title_layout, 1)
        header_layout.addWidget(summary_badge, alignment=Qt.AlignRight | Qt.AlignVCenter)
        root_layout.addLayout(header_layout)

        # Category Filter Tabs
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(Spacing.SM)

        categories = ["All", "Consistency", "Deep Work", "Planning", "Mastery"]
        self.filter_buttons = {}
        self.btn_group = QButtonGroup(self)

        for cat in categories:
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if cat == "All":
                btn.setChecked(True)
                btn.setObjectName("PrimaryButton")
            else:
                btn.setObjectName("GhostButton")
            btn.clicked.connect(lambda checked, c=cat: self.filter_category(c))
            self.filter_buttons[cat] = btn
            self.btn_group.addButton(btn)
            filter_layout.addWidget(btn)

        filter_layout.addStretch()
        root_layout.addLayout(filter_layout)

        # Scroll Area for Achievement Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.render_grid()
        root_layout.addWidget(self.scroll_area, 1)

        # Bottom Close Button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)

        root_layout.addLayout(bottom_layout)

    def filter_category(self, category):
        self.active_category = category
        for cat, btn in self.filter_buttons.items():
            if cat == category:
                btn.setObjectName("PrimaryButton")
                btn.setChecked(True)
            else:
                btn.setObjectName("GhostButton")
                btn.setChecked(False)
            btn.setStyle(btn.style())  # Force QSS refresh
        self.render_grid()

    def render_grid(self):
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
        layout.setSpacing(Spacing.MD)

        for ach_id, ach_info in ACHIEVEMENT_DEFINITIONS.items():
            if self.active_category != "All" and ach_info["category"] != self.active_category:
                continue

            unlock_rec = self.unlocked_dict.get(ach_id)
            card = AchievementCardWidget(ach_info, unlock_record=unlock_rec)
            layout.addWidget(card)

        layout.addStretch()
        self.scroll_area.setWidget(content_widget)
