"""The Project Ascend Insights window.

This module is deliberately presentation-only. All persisted-data aggregation,
comparisons, patterns, and recommendations are provided by InsightsService.
"""

from datetime import date
from statistics import median

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from Modules.calibration_service import (
    MIN_OBSERVATIONS_FOR_STATS,
    RECOMMENDATION_MIN_OBSERVATIONS,
    evidence_label,
    format_error_percent,
    format_plain_percent,
    recommended_estimate,
)
from Modules.date_utils import format_display_date
from Modules.insights_service import format_day_count, format_minutes
from UI.theme.design_system import Colors, ThemeManager


class MetricCard(QFrame):
    """Compact overview metric used by the Insights presentation."""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("InsightMetricTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("InsightMetricValue")
        self.note_label = QLabel()
        self.note_label.setObjectName("InsightMetricNote")
        self.note_label.setWordWrap(False)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_value(self, value, note=""):
        self.value_label.setText(value)
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))


class PatternCard(QFrame):
    """Small pattern panel that consumes already-calculated pattern data."""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("InsightPattern")
        self.setMinimumHeight(98)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("InsightMetricTitle")
        self.title_label = title_label
        self.value_label = QLabel("Not enough data yet")
        self.value_label.setObjectName("InsightPatternValue")
        self.value_label.setWordWrap(True)
        self.detail_label = QLabel()
        self.detail_label.setObjectName("InsightMetricNote")
        self.detail_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        layout.addStretch()

    def set_value(self, value, detail=""):
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))


class FocusTrendChart(QWidget):
    """A compact, responsive focus-time bar chart with no independent maths."""

    def __init__(self):
        super().__init__()
        self.points = ()
        self.hovered_index = None
        # A fixed height keeps the chart compact and guarantees the painted
        # bars always fit inside their container at every window size.
        self.setFixedHeight(172)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_points(self, points):
        self.points = tuple(points)
        self.hovered_index = None
        self.setToolTip("")
        self.update()

    def chart_geometry(self):
        """Return the shared bar geometry for painting and hover hit tests."""
        chart_left = 44
        chart_right = max(chart_left + 1, self.width() - 12)
        chart_top = 14
        chart_bottom = max(chart_top + 1, self.height() - 26)
        chart_height = chart_bottom - chart_top
        chart_width = chart_right - chart_left
        count = len(self.points)
        gap = max(4, min(10, chart_width // max(count * 6, 1)))
        bar_width = max(5, (chart_width - gap * (count - 1)) / count)
        return (
            chart_left,
            chart_right,
            chart_top,
            chart_bottom,
            chart_height,
            gap,
            bar_width,
        )

    def index_at_position(self, position):
        """Return the day column index under the pointer, or None."""
        if not self.points:
            return None

        chart_left, chart_right, _, _, _, gap, bar_width = self.chart_geometry()
        x_position = position.x()
        if x_position < chart_left or x_position > chart_right:
            return None

        slot_width = bar_width + gap
        index = int((x_position - chart_left) // slot_width)
        return min(max(index, 0), len(self.points) - 1)

    def point_at_position(self, position):
        """Return the day column under the pointer, including zero-value bars."""
        index = self.index_at_position(position)
        if index is None:
            return None
        return self.points[index]

    def set_hovered_index(self, index):
        """Repaint only when the highlighted column actually changes."""
        if index != self.hovered_index:
            self.hovered_index = index
            self.update()

    def mouseMoveEvent(self, event):
        index = self.index_at_position(event.position())
        self.set_hovered_index(index)

        if index is None:
            QToolTip.hideText()
            return super().mouseMoveEvent(event)

        QToolTip.showText(
            event.globalPosition().toPoint(),
            self.tooltip_for_point(self.points[index]),
            self,
        )
        event.accept()

    def leaveEvent(self, event):
        self.set_hovered_index(None)
        QToolTip.hideText()
        super().leaveEvent(event)

    @staticmethod
    def tooltip_for_point(point):
        """Format exact, per-day hover copy from one calculated trend point."""
        return (
            f"{format_display_date(point.day, include_weekday=True)}\n"
            f"Focus time: {format_minutes(point.focus_minutes)}"
        )

    @staticmethod
    def axis_label(minutes):
        """Compact y-axis caption for a whole number of minutes."""
        if minutes >= 60:
            hours = minutes / 60
            if abs(hours - round(hours)) < 0.05:
                return f"{int(round(hours))}h"
            return f"{hours:.1f}h"
        return f"{int(minutes)}m"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.points:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "No focus data yet")
            return

        maximum = max(point.focus_minutes for point in self.points)
        (
            chart_left,
            chart_right,
            chart_top,
            chart_bottom,
            chart_height,
            gap,
            bar_width,
        ) = self.chart_geometry()
        count = len(self.points)

        # Horizontal grid lines with compact axis captions.
        grid_font = painter.font()
        grid_font.setPointSizeF(7.5)
        painter.setFont(grid_font)
        divisions = 3
        for step in range(divisions + 1):
            ratio = step / divisions
            y = chart_bottom - ratio * chart_height
            painter.setPen(QColor(Colors.BORDER))
            painter.drawLine(chart_left, int(y), chart_right, int(y))

            # With no focus recorded the scale has no meaningful steps, so
            # label only the baseline instead of repeating "0m".
            if maximum <= 0 and step > 0:
                continue

            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                0,
                int(y) - 8,
                chart_left - 8,
                16,
                Qt.AlignRight | Qt.AlignVCenter,
                self.axis_label(maximum * ratio),
            )

        for index, point in enumerate(self.points):
            x = chart_left + index * (bar_width + gap)
            if maximum > 0:
                height = max(3, (point.focus_minutes / maximum) * chart_height)
            else:
                height = 3
            y = chart_bottom - height
            is_hovered = index == self.hovered_index

            painter.setPen(Qt.NoPen)
            if point.focus_minutes > 0:
                gradient = QLinearGradient(x, y, x, chart_bottom)
                top_color = (
                    QColor(Colors.PRIMARY_HOVER)
                    if is_hovered
                    else QColor(Colors.PRIMARY)
                )
                bottom_color = QColor(Colors.PRIMARY_PRESSED)
                bottom_color.setAlpha(210)
                gradient.setColorAt(0.0, top_color)
                gradient.setColorAt(1.0, bottom_color)
                painter.setBrush(gradient)
            else:
                # Zero-focus days keep a visible, hoverable baseline stub.
                painter.setBrush(
                    QColor(Colors.BORDER_STRONG if is_hovered else Colors.BORDER)
                )
            painter.drawRoundedRect(x, y, bar_width, height, 3, 3)

            if count == 1:
                label = "Today"
            elif count <= 7 or index == 0 or index == count - 1 or index % 5 == 0:
                label = point.day.strftime("%a")
            else:
                label = ""
            if label:
                painter.setPen(
                    QColor(
                        Colors.TEXT_SECONDARY if is_hovered else Colors.TEXT_MUTED
                    )
                )
                painter.drawText(
                    int(x),
                    chart_bottom + 6,
                    max(1, int(bar_width)),
                    14,
                    Qt.AlignHCenter | Qt.AlignTop,
                    label,
                )


class ConsistencyHeatmap(QWidget):
    """Calendar-style consistency view using levels supplied by the service."""

    LEVEL_COLORS = {
        "inactive": Colors.SURFACE_ELEVATED,
        "light": Colors.PRIMARY_MUTED,
        "moderate": Colors.PRIMARY,
        "high": Colors.SUCCESS,
    }

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(4)

    def set_days(self, heatmap_days):
        self.clear()
        day_count = len(heatmap_days)
        columns = 7 if day_count <= 7 else 10
        rows = max(1, (day_count + columns - 1) // columns)
        self.setMinimumHeight(rows * 42)
        for index, heatmap_day in enumerate(heatmap_days):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(3)

            weekday_label = QLabel(heatmap_day.day.strftime("%a")[0])
            weekday_label.setAlignment(Qt.AlignCenter)
            weekday_label.setObjectName("HeatmapDayLabel")

            block = QFrame()
            block.setFixedHeight(20)
            block.setStyleSheet(
                "background-color: "
                f"{self.LEVEL_COLORS[heatmap_day.level]}; "
                f"border: 1px solid {Colors.BORDER}; "
                "border-radius: 4px;"
            )
            tooltip = (
                f"{format_display_date(heatmap_day.day)}: "
                f"{format_minutes(heatmap_day.focus_minutes)} focused"
            )
            cell.setToolTip(tooltip)
            block.setToolTip(tooltip)

            cell_layout.addWidget(weekday_label)
            cell_layout.addWidget(block)
            row, column = divmod(index, columns)
            self.grid.addWidget(cell, row, column)

        for column in range(columns):
            self.grid.setColumnStretch(column, 1)

    def clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()


class AnalyticsWindow(QWidget):
    """Production Insights page rendered from a centralized data model."""

    def __init__(self, insights_service):
        super().__init__()
        self.insights_service = insights_service
        self.selected_range = "7_days"
        self.dashboard_data = None
        self.range_buttons = {}

        self.setWindowTitle("Project Ascend - Insights")
        self.apply_styles()
        self.build_ui()
        self.refresh()

    def apply_styles(self):
        # All Insights styling now lives in the centralized design system.
        self.setStyleSheet(ThemeManager.app_stylesheet())

    def header_actions(self):
        """Return the range filter buttons for the shell page header."""
        return tuple(self.range_buttons.values())

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(24, 18, 24, 24)
        self.content_layout.setSpacing(14)

        self.content_layout.addLayout(self.create_header())
        self.content_layout.addWidget(self.create_overview_section())
        self.content_layout.addWidget(self.create_focus_trends_section())
        self.content_layout.addWidget(self.create_patterns_section())
        self.content_layout.addWidget(self.create_calibration_section())
        self.content_layout.addWidget(self.create_consistency_section())
        self.content_layout.addWidget(self.create_insights_section())
        self.content_layout.addStretch()

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def create_header(self):
        """Build the in-page context line and the shared range filter buttons.

        The range buttons are created here but displayed by the application
        shell's page header, so the page itself stays free of a second title.
        """
        layout = QHBoxLayout()
        layout.setSpacing(16)

        self.current_date_label = QLabel(format_display_date(date.today()))
        self.current_date_label.setObjectName("MutedText")

        self.range_caption_label = QLabel()
        self.range_caption_label.setObjectName("MutedText")

        self.range_group = QButtonGroup(self)
        for key, text in (
            ("today", "Today"),
            ("7_days", "7 Days"),
            ("30_days", "30 Days"),
        ):
            button = QPushButton(text)
            button.setObjectName("RangeButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, range_key=key: self.select_range(range_key)
            )
            self.range_group.addButton(button)
            self.range_buttons[key] = button
        self.range_buttons[self.selected_range].setChecked(True)

        layout.addWidget(self.current_date_label)
        layout.addStretch()
        layout.addWidget(self.range_caption_label)
        return layout

    def create_overview_section(self):
        section, layout = self.create_section("Overview")
        self.overview_grid = QGridLayout()
        self.overview_grid.setContentsMargins(0, 0, 0, 0)
        self.overview_grid.setSpacing(10)
        self.overview_cards = {
            "focus": MetricCard("Focus Time"),
            "tasks": MetricCard("Tasks Completed"),
            "completion": MetricCard("Completion Rate"),
            "streak": MetricCard("Current Streak"),
            "xp": MetricCard("XP Earned"),
        }
        for column, card in enumerate(self.overview_cards.values()):
            self.overview_grid.addWidget(card, 0, column)
            self.overview_grid.setColumnStretch(column, 1)
        layout.addLayout(self.overview_grid)
        return section

    def create_focus_trends_section(self):
        section, layout = self.create_section("Focus Trends")

        header = QHBoxLayout()
        self.trend_summary_label = QLabel()
        self.trend_summary_label.setObjectName("MutedText")
        self.trend_comparison_label = QLabel()
        header.addWidget(self.trend_summary_label)
        header.addStretch()
        header.addWidget(self.trend_comparison_label)

        self.trend_chart = FocusTrendChart()
        layout.addLayout(header)
        layout.addWidget(self.trend_chart)
        return section

    def create_patterns_section(self):
        section, layout = self.create_section("Productivity Patterns")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.best_day_card = PatternCard("Best Day")
        self.best_time_card = PatternCard("Best Time")
        self.best_category_card = PatternCard("Most Productive Category")
        for column, card in enumerate((
            self.best_day_card,
            self.best_time_card,
            self.best_category_card,
        )):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        self.productive_days_label = QLabel()
        self.productive_days_label.setObjectName("MutedText")
        layout.addLayout(grid)
        layout.addWidget(self.productive_days_label)
        return section

    def create_calibration_section(self):
        section, layout = self.create_section("Planning Accuracy")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.bias_card = PatternCard("Estimate Bias")
        self.typical_error_card = PatternCard("Typical Error")
        self.confidence_card = PatternCard("Confidence")
        for column, card in enumerate((
            self.bias_card,
            self.typical_error_card,
            self.confidence_card,
        )):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        self.calibration_note_label = QLabel()
        self.calibration_note_label.setObjectName("MutedText")
        self.calibration_note_label.setWordWrap(True)
        layout.addLayout(grid)
        layout.addWidget(self.calibration_note_label)
        return section

    def create_consistency_section(self):
        section, layout = self.create_section("Consistency")
        self.heatmap = ConsistencyHeatmap()
        self.heatmap.setMinimumHeight(56)
        layout.addWidget(self.heatmap)

        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        for level, label in (
            ("inactive", "Inactive"),
            ("light", "Light"),
            ("moderate", "Moderate"),
            ("high", "Goal met"),
        ):
            marker = QLabel("  ")
            marker.setFixedSize(14, 14)
            marker.setStyleSheet(
                "background-color: "
                f"{ConsistencyHeatmap.LEVEL_COLORS[level]}; "
                "border-radius: 4px;"
            )
            legend_label = QLabel(label)
            legend_label.setObjectName("InsightMetricNote")
            legend_layout.addWidget(marker)
            legend_layout.addWidget(legend_label)
        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        stats_layout = QGridLayout()
        stats_layout.setContentsMargins(0, 4, 0, 0)
        stats_layout.setHorizontalSpacing(10)
        self.consistency_stats = {
            "current": self.create_consistency_stat("Current Streak"),
            "best": self.create_consistency_stat("Best Streak"),
            "active": self.create_consistency_stat("Active Days"),
            "goal": self.create_consistency_stat("Daily Goal Success"),
        }
        for column, card in enumerate(self.consistency_stats.values()):
            stats_layout.addWidget(card, 0, column)
            stats_layout.setColumnStretch(column, 1)
        layout.addLayout(stats_layout)
        return section

    def create_insights_section(self):
        section, layout = self.create_section("Your Insights")
        self.insights_layout = QVBoxLayout()
        self.insights_layout.setContentsMargins(0, 0, 0, 0)
        self.insights_layout.setSpacing(8)
        layout.addLayout(self.insights_layout)
        return section

    def create_section(self, title):
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)
        return section, layout

    def create_consistency_stat(self, title):
        card = QFrame()
        card.setObjectName("InsightMetric")
        card.setMinimumHeight(62)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("InsightMetricTitle")
        value_label = QLabel("—")
        value_label.setObjectName("InsightPatternValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        card.value_label = value_label
        return card

    def select_range(self, range_key):
        if range_key == self.selected_range:
            return
        self.selected_range = range_key
        self.range_buttons[range_key].setChecked(True)
        self.refresh()

    def load_statistics(self):
        """Compatibility entry point used by the application controller."""
        self.refresh()

    def refresh(self):
        self.current_date_label.setText(format_display_date(date.today()))
        self.dashboard_data = self.insights_service.build_dashboard(
            self.selected_range
        )
        self.render_dashboard(self.dashboard_data)

    def render_dashboard(self, data):
        overview = data.overview
        self.overview_cards["focus"].set_value(
            format_minutes(overview.focus_minutes),
            data.range_definition.label,
        )
        self.overview_cards["tasks"].set_value(
            str(overview.completed_tasks),
            f"of {overview.total_tasks} planned",
        )
        completion_note = (
            "No activities in this range"
            if overview.total_tasks == 0
            else f"{overview.completed_tasks} completed"
        )
        self.overview_cards["completion"].set_value(
            f"{overview.completion_rate}%",
            completion_note,
        )
        self.overview_cards["streak"].set_value(
            format_day_count(overview.current_streak),
            "Daily-goal streak",
        )
        if overview.xp_earned is None:
            self.overview_cards["xp"].set_value("0 XP", overview.xp_status)
        else:
            self.overview_cards["xp"].set_value(
                f"+{overview.xp_earned} XP",
                overview.xp_status or data.range_definition.label,
            )

        trend = data.trend
        self.trend_summary_label.setText(
            f"{format_minutes(trend.total_focus_minutes)} total  •  "
            f"{format_minutes(trend.daily_average_minutes)} daily average"
        )
        comparison_object_name = {
            "positive": "TrendComparisonPositive",
            "negative": "TrendComparisonNegative",
            "neutral": "TrendComparisonNeutral",
        }[trend.comparison.direction]
        self.trend_comparison_label.setObjectName(comparison_object_name)
        self.trend_comparison_label.setText(trend.comparison.text)
        self.trend_comparison_label.style().unpolish(self.trend_comparison_label)
        self.trend_comparison_label.style().polish(self.trend_comparison_label)
        self.trend_chart.set_points(trend.points)

        patterns = data.patterns
        if patterns.best_day_name is None:
            self.best_day_card.set_value(
                "No focus data yet",
                "Complete a session to identify a best day.",
            )
        else:
            self.best_day_card.set_value(
                patterns.best_day_name,
                f"{format_minutes(patterns.best_day_focus_minutes)} focused",
            )
        if patterns.best_time_label is None:
            self.best_time_card.set_value(
                "Not enough data yet",
                "Timestamped sessions unlock this pattern.",
            )
        else:
            self.best_time_card.set_value(
                patterns.best_time_label,
                f"{format_minutes(patterns.best_time_focus_minutes)} focused",
            )
        if patterns.best_category_name is None:
            self.best_category_card.set_value(
                "No focus data yet",
                "Complete a session to identify a category.",
            )
        else:
            self.best_category_card.set_value(
                patterns.best_category_name,
                f"{format_minutes(patterns.best_category_focus_minutes)} focused",
            )
        self.productive_days_label.setText(
            f"Productive: {format_day_count(patterns.active_days)} out of "
            f"{format_day_count(patterns.period_days)}. "
            "A productive day has completed work or recorded focus time."
        )

        consistency = data.consistency
        self.heatmap.set_days(consistency.heatmap_days)
        self.consistency_stats["current"].value_label.setText(
            format_day_count(consistency.current_streak)
        )
        self.consistency_stats["best"].value_label.setText(
            format_day_count(consistency.best_streak)
        )
        self.consistency_stats["active"].value_label.setText(
            f"{format_day_count(consistency.active_days)} / "
            f"{format_day_count(consistency.period_days)}"
        )
        self.consistency_stats["goal"].value_label.setText(
            f"{consistency.goal_success_rate}%"
        )

        self.render_calibration(data.calibration)
        self.render_insights(data.insights)

    def render_calibration(self, calibration):
        """Render the all-time Planning Accuracy section.

        This section never invents intelligence: without enough completed
        observations it explicitly says so instead of showing a number.
        Once a recommendation exists, the PRIMARY message is a realistic
        duration in minutes; percentages and the historical factor stay
        supporting copy.
        """
        summary = calibration.summary
        sample_count = summary.sample_count

        if sample_count < MIN_OBSERVATIONS_FOR_STATS:
            self.set_calibration_card_titles()
            self.bias_card.set_value(
                "Not enough data yet",
                "Complete at least 3 activities to begin calibration.",
            )
            self.typical_error_card.set_value(
                "Not enough data yet",
                "Calibration needs completed activities with focus time.",
            )
            self.confidence_card.set_value(
                evidence_label(summary.evidence_level),
                "No recommendation yet.",
            )
            self.calibration_note_label.setText(
                "Estimate calibration compares the ORIGINAL plan of a "
                "completed activity against its actual duration. Incomplete "
                "work is never counted."
            )
            return

        if summary.suggested_multiplier is None:
            self.set_calibration_card_titles()
            self.render_early_signal_calibration(calibration)
            return

        self.render_recommendation_calibration(calibration)

    def set_calibration_card_titles(self):
        """Restore the analytic titles used before a recommendation exists."""
        self.bias_card.title_label.setText("Estimate Bias")
        self.typical_error_card.title_label.setText("Typical Error")

    def render_early_signal_calibration(self, calibration):
        """Percentage presentation used while evidence is still growing.

        No multiplier exists yet, so no time recommendation is invented;
        the raw statistics are shown exactly as computed by the service.
        """
        summary = calibration.summary
        sample_count = summary.sample_count

        self.bias_card.set_value(
            format_error_percent(summary.mean_relative_error),
            (
                f"Average error across {sample_count} completed "
                "activities (all-time)"
            ),
        )
        self.typical_error_card.set_value(
            format_plain_percent(summary.mean_absolute_percentage_error),
            "Typical deviation from the estimate",
        )
        self.confidence_card.set_value(
            evidence_label(summary.evidence_level),
            f"{sample_count} observations • no recommendation yet",
        )

        note_parts = self.build_calibration_note_parts(calibration)
        note_parts.append(
            "Realistic time suggestions unlock at "
            f"{RECOMMENDATION_MIN_OBSERVATIONS} completed activities."
        )
        self.calibration_note_label.setText(" • ".join(note_parts))

    def render_recommendation_calibration(self, calibration):
        """Time-first presentation once a recommendation is available.

        WHAT SHOULD I DO?  -> "Plan ~68 min" (realistic duration)
        WHY?               -> "About 8 min more than your estimate"
        HOW RELIABLE?      -> "Based on 45 completed activities"

        The realistic duration comes from the user's own typical plan and
        the calibrated multiplier, rounded by the existing
        recommended_estimate() logic. No calibration mathematics is
        reimplemented here; percentages and the factor remain supporting
        copy in the note line.
        """
        summary = calibration.summary
        sample_count = summary.sample_count
        multiplier = summary.suggested_multiplier

        # A representative "typical plan" taken from the user's own
        # completed observations, so the recommendation is a concrete
        # duration instead of an abstract percentage. The median is robust
        # to outlier estimates and is rounded to whole minutes for display.
        typical_estimate = int(round(median(
            observation.estimated_minutes
            for observation in calibration.observations
        )))
        realistic_minutes = recommended_estimate(typical_estimate, multiplier)
        difference_minutes = realistic_minutes - typical_estimate

        self.bias_card.title_label.setText("Realistic Estimate")
        self.bias_card.set_value(
            f"~{realistic_minutes} min",
            f"For a typical {typical_estimate}-min plan",
        )

        self.typical_error_card.title_label.setText("Time Difference")
        if difference_minutes == 0:
            self.typical_error_card.set_value(
                "On target",
                "Your plans usually match reality",
            )
        elif difference_minutes > 0:
            self.typical_error_card.set_value(
                f"+{difference_minutes} min",
                "More than your original estimate",
            )
        else:
            self.typical_error_card.set_value(
                f"{difference_minutes} min",
                "Less than your original estimate",
            )

        self.confidence_card.set_value(
            evidence_label(summary.evidence_level),
            f"Based on {sample_count} completed activities",
        )

        note_parts = self.build_calibration_note_parts(calibration)
        note_parts.append(f"Historical planning factor ×{multiplier:.2f}")
        self.calibration_note_label.setText(" • ".join(note_parts))

    def build_calibration_note_parts(self, calibration):
        """Supporting copy shared by the calibration presentation states."""
        note_parts = []
        best_calibrated = self.best_calibrated_category(calibration)
        most_variable = self.most_variable_category(calibration)
        if best_calibrated is not None:
            note_parts.append(
                f"Best calibrated: {best_calibrated.activity_type} "
                f"({format_error_percent(best_calibrated.mean_relative_error)}, "
                f"{best_calibrated.sample_count} samples)"
            )
        if most_variable is not None and most_variable is not best_calibrated:
            note_parts.append(
                f"Most variable: {most_variable.activity_type} "
                f"({format_plain_percent(most_variable.mean_absolute_percentage_error)}, "
                f"{most_variable.sample_count} samples)"
            )
        if not note_parts:
            note_parts.append(
                "Category-level calibration unlocks as a category reaches "
                f"{MIN_OBSERVATIONS_FOR_STATS} completed activities."
            )
        return note_parts

    @staticmethod
    def best_calibrated_category(calibration):
        """Category with the smallest average error (closest to the plan)."""
        best = None
        for category in calibration.categories:
            if category.sample_count < MIN_OBSERVATIONS_FOR_STATS:
                continue
            if category.mean_relative_error is None:
                continue
            if (
                best is None
                or abs(category.mean_relative_error)
                < abs(best.mean_relative_error)
            ):
                best = category
        return best

    @staticmethod
    def most_variable_category(calibration):
        """Category with the largest typical error (least predictable)."""
        most_variable = None
        for category in calibration.categories:
            if category.sample_count < MIN_OBSERVATIONS_FOR_STATS:
                continue
            if category.mean_absolute_percentage_error is None:
                continue
            if (
                most_variable is None
                or category.mean_absolute_percentage_error
                > most_variable.mean_absolute_percentage_error
            ):
                most_variable = category
        return most_variable

    def render_insights(self, insights):
        self.clear_layout(self.insights_layout)
        for insight in insights:
            self.insights_layout.addWidget(self.create_insight_item(insight))

    def create_insight_item(self, insight):
        frame = QFrame()
        frame.setObjectName("InsightItem")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(10)

        icon, color = {
            "positive": ("↑", Colors.SUCCESS),
            "warning": ("!", "#F87171"),
            "goal": ("•", Colors.PRIMARY),
            "pattern": ("◈", Colors.ACCENT),
            "streak": ("↑", "#F59E0B"),
            "recommendation": ("→", Colors.PRIMARY_HOVER),
            "info": ("i", Colors.TEXT_MUTED),
        }.get(insight.kind, ("i", Colors.TEXT_MUTED))
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(26, 26)
        icon_label.setStyleSheet(
            f"background-color: {color}; color: {Colors.BACKGROUND}; "
            "border-radius: 13px; font-size: 15px; font-weight: 800;"
        )

        copy_layout = QVBoxLayout()
        copy_layout.setSpacing(2)
        title_label = QLabel(insight.title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 750;")
        description_label = QLabel(insight.description)
        description_label.setObjectName("InsightMetricNote")
        description_label.setWordWrap(True)
        copy_layout.addWidget(title_label)
        copy_layout.addWidget(description_label)

        layout.addWidget(icon_label, alignment=Qt.AlignTop)
        layout.addLayout(copy_layout, 1)
        if insight.metric:
            metric_label = QLabel(insight.metric)
            metric_label.setObjectName("InsightPatternValue")
            metric_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(metric_label)
        return frame

    @staticmethod
    def clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
