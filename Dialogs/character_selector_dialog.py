"""Character Selection Modal Dialog."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
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

from Modules.character_asset_manager import CHARACTER_MANIFEST, CharacterAssetManager
from Modules.character_manager import get_evolution_stage
from UI.theme.design_system import Colors, Radius, Spacing, Typography


class CharacterOptionCard(QFrame):
    """Card representing one of the 8 character identity archetypes."""

    character_selected = Signal(str)

    def __init__(self, character_info, current_stage=1, is_selected=False, asset_mgr=None):
        super().__init__()
        self.character_id = character_info["id"]
        self.asset_mgr = asset_mgr or CharacterAssetManager()

        self.setObjectName("InsightItem")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if is_selected:
            self.setProperty("selected", "true")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(Spacing.MD)

        # Avatar thumbnail
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(54, 54)
        pixmap = self.asset_mgr.get_character_pixmap(self.character_id, stage=current_stage, width=54, height=54)
        self.avatar_label.setPixmap(pixmap)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        self.name_label = QLabel(character_info["name"])
        self.name_label.setObjectName("Greeting")

        identity_text = character_info.get("identity") or character_info.get("title", "")
        self.identity_label = QLabel(identity_text)
        self.identity_label.setObjectName("MutedText")

        title_layout.addWidget(self.name_label)
        title_layout.addWidget(self.identity_label)

        top_layout.addWidget(self.avatar_label)
        top_layout.addLayout(title_layout, 1)

        layout.addLayout(top_layout)

        # Description
        desc_label = QLabel(character_info["description"])
        desc_label.setObjectName("MutedText")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Action Button / Status Indicator
        action_layout = QHBoxLayout()
        stage_info = get_evolution_stage(current_stage)
        stage_label = QLabel(f"Stage {stage_info['stage']} — {stage_info['name']}")
        stage_label.setObjectName("Badge")

        action_layout.addWidget(stage_label)
        action_layout.addStretch()

        if is_selected:
            status_badge = QLabel("Active Identity")
            status_badge.setObjectName("CompletedBadge")
            action_layout.addWidget(status_badge)
        else:
            self.select_btn = QPushButton("Select Archetype")
            self.select_btn.setObjectName("PrimaryButton")
            self.select_btn.setCursor(Qt.PointingHandCursor)
            self.select_btn.clicked.connect(self._on_select_clicked)
            action_layout.addWidget(self.select_btn)

        layout.addLayout(action_layout)

    def _on_select_clicked(self):
        self.character_selected.emit(self.character_id)


class CharacterSelectorDialog(QDialog):
    """Non-destructive character archetype selection modal."""

    character_changed = Signal(str)

    def __init__(self, character_manager, current_level=1, parent=None):
        super().__init__(parent)
        self.character_manager = character_manager
        self.current_level = current_level
        self.asset_mgr = CharacterAssetManager()

        self.setWindowTitle("Select Identity Archetype")
        self.setMinimumSize(780, 580)
        self.resize(840, 620)

        self.build_ui()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        root_layout.setSpacing(Spacing.LG)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title = QLabel("Identity Archetypes")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Choose your visual character representation. Identity selection is purely cosmetic.")
        subtitle.setObjectName("MutedText")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root_layout.addLayout(header_layout)

        # Scroll Area for Character Cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        grid_layout = QGridLayout(content_widget)
        grid_layout.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
        grid_layout.setSpacing(Spacing.LG)

        current_selected_id = self.character_manager.get_selected_character_id()
        characters = self.character_manager.get_characters()

        # Render 2-column grid of 8 character archetypes
        for idx, char_info in enumerate(characters):
            row = idx // 2
            col = idx % 2
            is_sel = (char_info["id"] == current_selected_id)

            card = CharacterOptionCard(
                char_info,
                current_stage=self.current_level,
                is_selected=is_sel,
                asset_mgr=self.asset_mgr,
            )
            card.character_selected.connect(self.select_character)
            grid_layout.addWidget(card, row, col)

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area, 1)

        # Bottom Close Button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)

        root_layout.addLayout(bottom_layout)

    def select_character(self, character_id):
        """Persist selected character and close dialog."""
        success = self.character_manager.set_selected_character(character_id)
        if success:
            self.character_changed.emit(character_id)
            self.accept()
