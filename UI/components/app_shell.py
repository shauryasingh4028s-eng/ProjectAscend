"""The Project Ascend application shell.

The shell provides the persistent sidebar, the page header and the page stack.
It is presentation-only: it hosts the existing screen widgets unchanged and
never performs analytics, XP or database work of its own.

Adding a future module is a single ``add_page`` call, so new sections do not
require another shell redesign.
"""
import sys
from pathlib import Path
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from UI.components.celebrations import CelebrationOverlay
from UI.theme.design_system import (
    BrandAssets,
    Colors,
    IconFactory,
    Spacing,
    ThemeManager,
)


class SidebarPlayerCard(QFrame):
    """Compact level/XP summary pinned to the bottom of the sidebar."""

    def __init__(self):
        super().__init__()
        self.setObjectName("SidebarPlayerCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM + 2, Spacing.MD, Spacing.SM + 2)
        layout.setSpacing(Spacing.XS + 2)

        identity_layout = QHBoxLayout()
        identity_layout.setSpacing(Spacing.SM)

        self.avatar_label = QLabel("PA")
        self.avatar_label.setObjectName("SidebarPlayerAvatar")
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setFixedSize(30, 30)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)
        # Styled by object name so the name follows the active theme's
        # primary text colour instead of freezing the colour that was
        # active when the card was built.
        self.name_label = QLabel("Ascender")
        self.name_label.setObjectName("SidebarPlayerName")
        self.level_label = QLabel("Level 1")
        self.level_label.setObjectName("MutedText")
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.level_label)

        identity_layout.addWidget(self.avatar_label)
        identity_layout.addLayout(text_layout, 1)

        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("XpBar")
        self.xp_bar.setRange(0, 100)
        self.xp_bar.setValue(0)
        self.xp_bar.setTextVisible(False)

        self.xp_label = QLabel("0 / 100 XP")
        self.xp_label.setObjectName("MutedText")

        layout.addLayout(identity_layout)
        layout.addWidget(self.xp_bar)
        layout.addWidget(self.xp_label)

    def set_name(self, name):
        clean_name = (name or "Ascender").strip() or "Ascender"
        self.name_label.setText(clean_name)
        initials = "".join(part[0] for part in clean_name.split()[:2]).upper() or "A"
        self.avatar_label.setText(initials[:2])

    def set_progress(self, level, xp_into_level, xp_for_level, total_xp):
        """Display already-calculated progression values."""
        self.level_label.setText(f"Level {level}")
        self.xp_bar.setRange(0, max(1, xp_for_level))
        self.xp_bar.setValue(max(0, min(xp_into_level, xp_for_level)))
        self.xp_label.setText(f"{total_xp:,} XP  •  {xp_into_level}/{xp_for_level}")


class Sidebar(QFrame):
    """Scalable navigation rail with brand, sections and player summary."""

    navigation_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(214)

        self.nav_buttons = {}
        self.nav_icon_names = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.icon_factory = IconFactory(self)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(Spacing.MD, Spacing.LG, Spacing.MD, Spacing.MD)
        self.layout.setSpacing(Spacing.SM)

        self.layout.addWidget(self._create_brand())
        self.layout.addSpacing(Spacing.MD)

        self.nav_layout = QVBoxLayout()
        self.nav_layout.setSpacing(2)
        self.layout.addLayout(self.nav_layout)
        self.layout.addStretch(1)

        self.player_card = SidebarPlayerCard()
        self.layout.addWidget(self.player_card)

    def _create_brand(self):
        """Create the Ascend brand lockup using the real application logo."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(Spacing.XS, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        logo = QLabel()
        logo.setFixedSize(28, 28)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background: transparent; border: none;")

        # Keep the logo asset in Assets/ so it is shared by source and
        # packaged builds. Fall back gracefully if the asset is unavailable.
        from pathlib import Path

        if getattr(sys, "frozen", False):
            project_root = Path(sys._MEIPASS)
        else:
            project_root = Path(__file__).resolve().parents[2]

        logo_path = project_root / "Assets" / "logo_32.png"
        self.logo_source = QPixmap(str(logo_path))
        self.logo_label = logo
        if self.logo_source.isNull():
            logo.setText("▲")
            logo.setStyleSheet(
                f"color: {Colors.PRIMARY}; font-size: 15px; font-weight: 800;"
            )
        else:
            self.refresh_brand_mark()

        name = QLabel("ASCEND")
        name.setObjectName("BrandMark")

        layout.addWidget(logo)
        layout.addWidget(name)
        layout.addStretch()
        return container

    def refresh_brand_mark(self):
        """Re-ink the brand mark for the active theme (same size/placement)."""
        source = getattr(self, "logo_source", None)
        if source is None or source.isNull():
            return

        self.logo_label.setPixmap(
            BrandAssets.themed_logo(source).scaled(
                26,
                26,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def add_section_label(self, text):
        label = QLabel(text.upper())
        label.setObjectName("SidebarSectionLabel")
        label.setContentsMargins(Spacing.SM, Spacing.SM, 0, 2)
        self.nav_layout.addWidget(label)

    def add_nav_item(self, key, text, icon_name):
        button = QPushButton(text)
        button.setObjectName("NavItem")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setIcon(self.icon_factory.get(icon_name, Colors.TEXT_SECONDARY))
        button.setIconSize(QSize(15, 15))
        button.clicked.connect(
            lambda _checked=False, nav_key=key: self.navigation_requested.emit(nav_key)
        )
        self.button_group.addButton(button)
        self.nav_layout.addWidget(button)
        self.nav_buttons[key] = button
        self.nav_icon_names[button] = icon_name
        return button

    def set_active(self, key):
        button = self.nav_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def refresh_theme(self):
        """Re-render the sidebar's painted assets for the active theme.

        Stylesheet-driven colours follow the theme automatically; the brand
        pixmap and the navigation icons are painted once at build time, so
        they are re-inked here when the theme changes.
        """
        self.refresh_brand_mark()
        for button in self.nav_buttons.values():
            icon_name = self.nav_icon_names.get(button)
            if icon_name is not None:
                button.setIcon(
                    self.icon_factory.get(icon_name, Colors.TEXT_SECONDARY)
                )


class PageHeader(QFrame):
    """Header strip showing the current page title plus contextual actions."""

    def __init__(self):
        super().__init__()
        self.setObjectName("PageHeader")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, 0, Spacing.XXL, 0)
        layout.setSpacing(Spacing.MD)

        self.title_label = QLabel("Dashboard")
        self.title_label.setObjectName("PageTitle")

        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(Spacing.SM)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addLayout(self.actions_layout)

    def set_title(self, title):
        self.title_label.setText(title)

    def set_actions(self, widgets):
        """Show only the action widgets belonging to the current page."""
        while self.actions_layout.count():
            item = self.actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        for widget in widgets:
            widget.setParent(self)
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            widget.setCursor(Qt.PointingHandCursor)
            widget.show()
            self.actions_layout.addWidget(widget)


class AppShell(QWidget):
    """Main window: sidebar + header + stacked pages."""

    page_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("AppShell")
        self.setWindowTitle("Project Ascend")
        self.resize(1280, 840)
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(ThemeManager.app_stylesheet())

        self.pages = {}
        self.page_titles = {}
        self.page_actions = {}

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigation_requested.connect(self.show_page)

        canvas = QWidget()
        canvas.setObjectName("PageCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.header = PageHeader()
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageBody")

        canvas_layout.addWidget(self.header)
        canvas_layout.addWidget(self.stack, 1)

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(canvas, 1)

        # A single non-blocking surface handles only meaningful progression
        # celebrations. Ordinary navigation and task actions remain static.
        self.celebration_overlay = CelebrationOverlay(self)
        self.celebration_overlay.setGeometry(self.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "celebration_overlay"):
            self.celebration_overlay.setGeometry(self.rect())

    def show_celebration(self, celebration):
        return self.celebration_overlay.enqueue(celebration)

    def add_section_label(self, text):
        self.sidebar.add_section_label(text)

    def add_page(self, key, title, icon_name, widget, actions=None):
        """Register one navigable page. Future modules use this same call."""
        self.pages[key] = widget
        self.page_titles[key] = title
        self.page_actions[key] = list(actions or ())
        self.sidebar.add_nav_item(key, title, icon_name)
        self.stack.addWidget(widget)
        return widget

    def show_page(self, key):
        widget = self.pages.get(key)
        if widget is None:
            return

        self.stack.setCurrentWidget(widget)
        self.header.set_title(self.page_titles[key])
        self.header.set_actions(self.page_actions[key])
        self.sidebar.set_active(key)
        self.page_changed.emit(key)

    def current_page_key(self):
        current = self.stack.currentWidget()
        for key, widget in self.pages.items():
            if widget is current:
                return key
        return None
