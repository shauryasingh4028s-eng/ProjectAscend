"""Centralized Project Ascend design system.

This module owns every visual token and the single application stylesheet.
Screens must not define competing palettes or ad-hoc colours; they reference
``Colors``/``Spacing``/``Radius`` and the shared object names below.

Nothing in this module performs business logic, database access or analytics.
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QStyle

try:
    import qtawesome as qta
except ImportError:
    qta = None


class Colors:
    """Semantic colour tokens for the whole application.

    Every token is theme-aware: ``ThemeManager.set_theme()`` rewrites the
    values below from the active theme palette. Structural values default
    to the dark ("Deep Focus") theme until a theme is selected.
    """

    # Structural surfaces.
    BACKGROUND = "#05070C"
    SIDEBAR = "#070A11"
    HEADER = "#080C13"
    SURFACE = "#0D1219"
    SURFACE_SECONDARY = "#101722"
    SURFACE_ELEVATED = "#131B27"
    SURFACE_HOVER = "#17212F"

    # Lines and separators.
    BORDER = "#1B2533"
    BORDER_STRONG = "#26344A"

    # Brand accents.
    PRIMARY = "#3B82F6"
    PRIMARY_HOVER = "#60A5FA"
    PRIMARY_PRESSED = "#2563EB"
    PRIMARY_SOFT = "#152C5E"
    PRIMARY_MUTED = "#1D3A78"
    ACCENT = "#7C5CFF"
    ACCENT_HOVER = "#9B7BFF"
    ACCENT_SOFT = "#241C4D"
    ACCENT_MUTED = "#2E2560"

    # Status colours.
    SUCCESS = "#22C55E"
    SUCCESS_HOVER = "#4ADE80"
    SUCCESS_SOFT = "#0C2E1E"
    WARNING = "#F59E0B"
    WARNING_SOFT = "#3A2A08"
    ERROR = "#EF4444"

    # Typography.
    TEXT_PRIMARY = "#F5F8FC"
    TEXT_SECONDARY = "#C3CDDB"
    TEXT_MUTED = "#7C8AA0"
    DISABLED = "#4E5A6D"


class Spacing:
    """Consistent 4px-based spacing scale."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24


class Radius:
    """Corner radius scale. Cards stay compact, never pill-shaped."""

    SM = 8
    MD = 10
    LG = 14
    XL = 18


class Typography:
    """Font sizes in px, matched to the product's hierarchy."""

    FAMILY = "Segoe UI, Inter, Roboto, sans-serif"
    PAGE_TITLE = 22
    SECTION_TITLE = 15
    CARD_TITLE = 12
    METRIC_VALUE = 26
    BODY = 13
    SECONDARY = 12
    LABEL = 11


class IconFactory:
    """Resolves themed icons, degrading safely when qtawesome is absent."""

    def __init__(self, widget):
        self.widget = widget

    def get(self, icon_name, color=Colors.TEXT_SECONDARY):
        if qta is not None:
            try:
                return qta.icon(icon_name, color=color)
            except Exception:
                pass

        return self.widget.style().standardIcon(QStyle.SP_ArrowRight)


class ButtonFactory:
    """Builds the shared button variants used across every screen."""

    def __init__(self, icon_factory):
        self.icon_factory = icon_factory

    def primary(self, text, icon_name):
        return self._button(
            text, icon_name, "PrimaryButton", 15, Colors.TEXT_PRIMARY
        )

    def secondary(self, text, icon_name):
        return self._button(
            text, icon_name, "GhostButton", 15, Colors.TEXT_SECONDARY
        )

    def success(self, text, icon_name):
        return self._button(
            text, icon_name, "SuccessButton", 15, Colors.TEXT_PRIMARY
        )

    def action(self, text, icon_name):
        button = self._button(
            text, icon_name, "ActionButton", 16, Colors.TEXT_SECONDARY
        )
        button.setMinimumHeight(42)
        return button

    def icon_button(self, icon_name):
        button = QPushButton()
        button.setObjectName("IconButton")
        button.setIcon(self.icon_factory.get(icon_name, Colors.TEXT_SECONDARY))
        button.setIconSize(QSize(15, 15))
        button.setFixedSize(34, 34)
        return button

    def _button(self, text, icon_name, object_name, icon_size, icon_color):
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setIcon(self.icon_factory.get(icon_name, icon_color))
        button.setIconSize(QSize(icon_size, icon_size))
        button.setMinimumHeight(36)
        return button


class ThemeManager:
    """Provides shadows, theme tokens and the application-wide stylesheet."""

    _themes = {
        # Dark: "Deep Focus" - the established premium identity. Brand and
        # status values are the original Ascend constants; nothing changes
        # visually except that they are now theme-managed like every other
        # token (shared components stay consistent).
        "dark": {
            "BACKGROUND": "#05070C", "SIDEBAR": "#070A11", "HEADER": "#080C13",
            "SURFACE": "#0D1219", "SURFACE_SECONDARY": "#101722", "SURFACE_ELEVATED": "#131B27",
            "SURFACE_HOVER": "#17212F", "BORDER": "#1B2533", "BORDER_STRONG": "#26344A",
            "TEXT_PRIMARY": "#F5F8FC", "TEXT_SECONDARY": "#C3CDDB", "TEXT_MUTED": "#7C8AA0",
            "DISABLED": "#4E5A6D",
            "PRIMARY_SOFT": "#152C5E", "PRIMARY_MUTED": "#1D3A78",
            "ACCENT_SOFT": "#241C4D", "ACCENT_MUTED": "#2E2560",
            "SUCCESS_SOFT": "#0C2E1E", "WARNING_SOFT": "#3A2A08",
            "PRIMARY": "#3B82F6", "PRIMARY_HOVER": "#60A5FA", "PRIMARY_PRESSED": "#2563EB",
            "ACCENT": "#7C5CFF", "ACCENT_HOVER": "#9B7BFF",
            "SUCCESS": "#22C55E", "SUCCESS_HOVER": "#4ADE80",
            "WARNING": "#F59E0B", "ERROR": "#EF4444",
        },
        # Light: "Clear Thinking" - an ambient, soft-neutral canvas. Warm
        # white surfaces, cool blue accents, washed semantic tints. Strong
        # colours are reserved for values and actions; colour never shouts.
        "light": {
            "BACKGROUND": "#F5F7FB", "SIDEBAR": "#EDF1F8", "HEADER": "#F8FAFD",
            "SURFACE": "#FFFFFF", "SURFACE_SECONDARY": "#F8F9FD", "SURFACE_ELEVATED": "#F1F4FC",
            "SURFACE_HOVER": "#EDF2FA", "BORDER": "#E3E8F0", "BORDER_STRONG": "#CBD5E4",
            "TEXT_PRIMARY": "#172033", "TEXT_SECONDARY": "#596579", "TEXT_MUTED": "#75819B",
            "DISABLED": "#B0BACB",
            # Washed tints: selected states, chips and heatmap cells read
            # correctly on white instead of inheriting dark-navy.
            "PRIMARY_SOFT": "#E8EEFF", "PRIMARY_MUTED": "#C7D8FB",
            "ACCENT_SOFT": "#EEEAFE", "ACCENT_MUTED": "#D8CFF7",
            "SUCCESS_SOFT": "#E5F6ED", "WARNING_SOFT": "#FFF3DD",
            # Deeper brand/status values so text on white stays accessible.
            "PRIMARY": "#3B6FF5", "PRIMARY_HOVER": "#4A78EE", "PRIMARY_PRESSED": "#2E5BD8",
            "ACCENT": "#7657E8", "ACCENT_HOVER": "#8B6FE8",
            "SUCCESS": "#26915F", "SUCCESS_HOVER": "#1F7A4D",
            "WARNING": "#AC7113", "ERROR": "#C94A4A",
        },
    }
    current_theme = "dark"

    @classmethod
    def set_theme(cls, theme):
        theme = theme if theme in cls._themes else "dark"
        cls.current_theme = theme
        palette = cls._themes[theme]
        for key, value in palette.items():
            setattr(Colors, key, value)

    @classmethod
    def toggle_theme(cls):
        cls.set_theme("light" if cls.current_theme == "dark" else "dark")
        return cls.current_theme


    @staticmethod
    def add_shadow(widget, blur=26, y_offset=6, alpha=120):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y_offset)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    @staticmethod
    def app_stylesheet():
        """Return the complete Project Ascend stylesheet."""
        return f"""
            QWidget {{
                background-color: {Colors.BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                font-family: {Typography.FAMILY};
                font-size: {Typography.BODY}px;
            }}

            QToolTip {{
                background-color: {Colors.SURFACE_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_STRONG};
                border-radius: {Radius.SM}px;
                padding: 7px 10px;
                font-size: {Typography.SECONDARY}px;
            }}

            /* ---------- Application shell ---------- */

            QFrame#Sidebar {{
                background-color: {Colors.SIDEBAR};
                border: none;
                border-right: 1px solid {Colors.BORDER};
            }}

            QLabel#BrandMark {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 1px;
            }}

            QLabel#SidebarSectionLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.LABEL}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}

            QPushButton#NavItem {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: {Radius.MD}px;
                color: {Colors.TEXT_SECONDARY};
                font-size: {Typography.BODY}px;
                font-weight: 600;
                padding: 9px 12px;
                text-align: left;
            }}

            QPushButton#NavItem:hover {{
                background-color: {Colors.SURFACE_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}

            QPushButton#NavItem:checked {{
                background-color: {Colors.PRIMARY_SOFT};
                border: 1px solid {Colors.PRIMARY_MUTED};
                color: {Colors.TEXT_PRIMARY};
                font-weight: 700;
            }}

            QFrame#SidebarPlayerCard {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.LG}px;
            }}

            QFrame#PageHeader {{
                background-color: {Colors.HEADER};
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
            }}

            QWidget#PageCanvas, QWidget#PageBody {{
                background-color: {Colors.BACKGROUND};
            }}

            /* ---------- Cards and surfaces ---------- */

            QFrame#HeroCard,
            QFrame#MetricCard,
            QFrame#PlayerCard,
            QFrame#ActivitySection,
            QFrame#ActionBar,
            QFrame#InsightSurface {{
                background-color: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.LG}px;
            }}

            /* The Focus card is the dashboard's primary surface: a soft
               brand border gives it the visual weight of "what matters
               right now" without competing with the primary action. */
            QFrame#FocusCard {{
                background-color: {Colors.SURFACE};
                border: 1px solid {Colors.PRIMARY_MUTED};
                border-radius: {Radius.LG}px;
            }}

            QFrame#StatTile,
            QFrame#CompactStatRow,
            QFrame#ActivityCard,
            QFrame#InsightMetric,
            QFrame#InsightPattern,
            QFrame#InsightItem {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.MD}px;
            }}

            QFrame#ActivityCard[selected="true"] {{
                background-color: {Colors.PRIMARY_SOFT};
                border: 1px solid {Colors.PRIMARY};
            }}

            QFrame#LearnedInsight {{
                background-color: {Colors.SURFACE};
                border: 1px solid {Colors.ACCENT_MUTED};
                border-radius: {Radius.LG}px;
            }}

            QLabel#MetricDeltaPositive {{
                color: {Colors.SUCCESS};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}

            QLabel#MetricDeltaNegative {{
                color: {Colors.ERROR};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}

            QLabel#MetricDeltaNeutral {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}

            QFrame#ActivityCard:hover,
            QFrame#StatTile:hover,
            QFrame#InsightMetric:hover,
            QFrame#InsightPattern:hover {{
                background-color: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER_STRONG};
            }}

            QLabel {{
                background: transparent;
                border: none;
            }}

            /* ---------- Typography ---------- */

            QLabel#PageTitle {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.PAGE_TITLE}px;
                font-weight: 800;
            }}

            QLabel#Greeting {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 17px;
                font-weight: 700;
            }}

            QLabel#MutedText {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SECONDARY}px;
            }}

            QLabel#SectionTitle {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SECTION_TITLE}px;
                font-weight: 750;
            }}

            QLabel#StatTitle,
            QLabel#InsightMetricTitle {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.CARD_TITLE}px;
                font-weight: 650;
            }}

            QLabel#StatValue,
            QLabel#InsightMetricValue {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.METRIC_VALUE}px;
                font-weight: 800;
            }}

            QLabel#PlayerLevel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 20px;
                font-weight: 800;
            }}

            QLabel#PlayerXp,
            QLabel#InsightMetricNote,
            QLabel#HeatmapDayLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SECONDARY}px;
            }}

            QLabel#CompactStatValue,
            QLabel#InsightPatternValue {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 750;
            }}

            QLabel#Timer {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 52px;
                font-weight: 800;
            }}

            QLabel#Badge {{
                color: {Colors.TEXT_SECONDARY};
                background-color: {Colors.SURFACE_ELEVATED};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.SM}px;
                padding: 3px 9px;
                font-size: {Typography.LABEL}px;
                font-weight: 650;
            }}

            QLabel#CompletedBadge {{
                color: {Colors.SUCCESS_HOVER};
                background-color: {Colors.SUCCESS_SOFT};
                border: 1px solid {Colors.SUCCESS};
                border-radius: {Radius.SM}px;
                padding: 3px 9px;
                font-size: {Typography.LABEL}px;
                font-weight: 700;
            }}

            QLabel#PlannedBadge {{
                color: {Colors.PRIMARY_HOVER};
                background-color: {Colors.PRIMARY_SOFT};
                border: 1px solid {Colors.PRIMARY_MUTED};
                border-radius: {Radius.SM}px;
                padding: 3px 9px;
                font-size: {Typography.LABEL}px;
                font-weight: 700;
            }}

            /* ---------- Buttons ---------- */

            QPushButton {{
                background-color: {Colors.SURFACE_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_STRONG};
                border-radius: {Radius.MD}px;
                padding: 8px 14px;
                font-size: {Typography.BODY}px;
                font-weight: 650;
            }}

            QPushButton:hover {{
                background-color: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.PRIMARY_MUTED};
            }}

            QPushButton:pressed {{
                background-color: {Colors.SURFACE_SECONDARY};
            }}

            QPushButton:disabled {{
                background-color: {Colors.SURFACE_SECONDARY};
                color: {Colors.DISABLED};
                border: 1px solid {Colors.BORDER};
            }}

            QPushButton#PrimaryButton {{
                background-color: {Colors.PRIMARY};
                border: 1px solid {Colors.PRIMARY};
                color: #FFFFFF;
                font-weight: 700;
            }}

            QPushButton#PrimaryButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
                border: 1px solid {Colors.PRIMARY_HOVER};
            }}

            QPushButton#PrimaryButton:pressed {{
                background-color: {Colors.PRIMARY_PRESSED};
            }}

            QPushButton#SuccessButton {{
                background-color: {Colors.SUCCESS};
                border: 1px solid {Colors.SUCCESS};
                color: #04120A;
                font-weight: 700;
            }}

            QPushButton#SuccessButton:hover {{
                background-color: {Colors.SUCCESS_HOVER};
                border: 1px solid {Colors.SUCCESS_HOVER};
            }}

            QPushButton#GhostButton,
            QPushButton#IconButton,
            QPushButton#ActionButton {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_SECONDARY};
            }}

            QPushButton#GhostButton:hover,
            QPushButton#IconButton:hover,
            QPushButton#ActionButton:hover {{
                background-color: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.PRIMARY_MUTED};
                color: {Colors.TEXT_PRIMARY};
            }}

            QPushButton#IconButton {{
                border-radius: {Radius.MD}px;
                padding: 6px;
            }}

            QPushButton#ActionButton {{
                border-radius: {Radius.MD}px;
                padding: 9px 14px;
                text-align: left;
            }}

            QPushButton#RangeButton {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.SM}px;
                color: {Colors.TEXT_MUTED};
                padding: 6px 14px;
                font-size: {Typography.SECONDARY}px;
                font-weight: 650;
            }}

            QPushButton#RangeButton:hover {{
                background-color: {Colors.SURFACE_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}

            QPushButton#RangeButton:checked {{
                background-color: {Colors.PRIMARY};
                border: 1px solid {Colors.PRIMARY};
                color: #FFFFFF;
                font-weight: 700;
            }}

            /* ---------- Progress ---------- */

            QProgressBar {{
                background-color: {Colors.SURFACE_ELEVATED};
                border: none;
                border-radius: 5px;
                max-height: 10px;
                min-height: 10px;
                text-align: center;
                color: transparent;
            }}

            QProgressBar::chunk {{
                background-color: {Colors.PRIMARY};
                border-radius: 5px;
            }}

            QProgressBar#XpBar::chunk {{
                background-color: {Colors.ACCENT};
            }}

            /* ---------- Inputs, lists and containers ---------- */

            QScrollArea, QScrollArea > QWidget > QWidget {{
                background-color: transparent;
                border: none;
            }}

            QScrollBar:vertical {{
                background-color: transparent;
                width: 9px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical {{
                background-color: {Colors.BORDER_STRONG};
                border-radius: 4px;
                min-height: 30px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {Colors.PRIMARY_MUTED};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QListWidget {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.MD}px;
                padding: 5px;
                outline: none;
            }}

            QListWidget::item {{
                background-color: transparent;
                border-radius: {Radius.SM}px;
                padding: 9px 10px;
                margin: 2px 0px;
                color: {Colors.TEXT_SECONDARY};
            }}

            QListWidget::item:hover {{
                background-color: {Colors.SURFACE_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}

            QListWidget::item:selected {{
                background-color: {Colors.PRIMARY_SOFT};
                color: {Colors.TEXT_PRIMARY};
            }}

            QMenu, QDialog, QSpinBox, QLineEdit, QComboBox {{
                background-color: {Colors.SURFACE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
            }}

            QMenu {{
                border-radius: {Radius.MD}px;
                padding: 5px;
            }}

            QMenu::item {{
                padding: 8px 18px;
                border-radius: {Radius.SM}px;
            }}

            QMenu::item:selected {{
                background-color: {Colors.PRIMARY_SOFT};
            }}

            QSpinBox, QLineEdit, QComboBox {{
                border-radius: {Radius.SM}px;
                padding: 8px 10px;
                selection-background-color: {Colors.PRIMARY};
            }}

            QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {Colors.PRIMARY};
            }}

            /* ---------- History entries ---------- */

            QFrame#HistoryEntry {{
                background-color: {Colors.SURFACE_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: {Radius.MD}px;
            }}

            QFrame#HistoryEntry:hover {{
                background-color: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.PRIMARY_MUTED};
            }}

            QLabel#HistoryDate {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 750;
            }}

            QLabel#HistoryWeekday {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.LABEL}px;
                font-weight: 650;
            }}

            QLabel#HistoryMetricLabel {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.LABEL}px;
                font-weight: 650;
            }}

            QLabel#HistoryMetricValue {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 750;
            }}

            QLabel#HistoryBadgeAchieved {{
                color: {Colors.SUCCESS_HOVER};
                background-color: {Colors.SUCCESS_SOFT};
                border: 1px solid {Colors.SUCCESS};
                border-radius: {Radius.SM}px;
                padding: 3px 10px;
                font-size: {Typography.LABEL}px;
                font-weight: 700;
            }}

            QLabel#HistoryBadgeMissed {{
                color: {Colors.WARNING};
                background-color: {Colors.WARNING_SOFT};
                border: 1px solid {Colors.WARNING};
                border-radius: {Radius.SM}px;
                padding: 3px 10px;
                font-size: {Typography.LABEL}px;
                font-weight: 700;
            }}

            /* ---------- Insights trend states ---------- */

            QLabel#TrendComparisonPositive {{
                color: {Colors.SUCCESS};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}

            QLabel#TrendComparisonNegative {{
                color: {Colors.ERROR};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}

            QLabel#TrendComparisonNeutral {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SECONDARY}px;
                font-weight: 700;
            }}
        """

    @staticmethod
    def dashboard_stylesheet():
        """Backwards-compatible alias kept for existing screens."""
        return ThemeManager.app_stylesheet()
