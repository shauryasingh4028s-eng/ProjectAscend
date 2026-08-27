"""The Project Ascend Insights window.

This module is deliberately presentation-only. All persisted-data aggregation,
comparisons, patterns, and recommendations are provided by InsightsService.
"""

from datetime import date
from statistics import median

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
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

from UI.theme.motion_utils import (
    CHART_BAR_DURATION,
    CHART_TREND_DURATION,
    is_reduced_motion_enabled,
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
from Modules.insights_service import (
    LearnedInsight,
    comparison_caption,
    format_day_count,
    format_minutes,
)
from UI.theme.design_system import Colors, IconFactory, Radius, ThemeManager


class MetricCard(QFrame):
    """Compact overview metric used by the Insights presentation.

    ``tint`` (blue / green / purple / amber / None) gives the card a soft
    semantic background and its value a strong matching colour, so each
    metric's meaning is visible at a glance. Styling comes from the shared
    stylesheet property selectors, keeping both themes consistent.
    """

    def __init__(self, title, tint=None, tone=None):
        super().__init__()
        self.setObjectName("InsightMetric")
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("InsightMetricTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("InsightMetricValue")
        if tone:
            self.value_label.setProperty("tone", tone)
        self.delta_label = QLabel()
        self.delta_label.setObjectName("MetricDeltaNeutral")
        self.delta_label.setVisible(False)
        self.note_label = QLabel()
        self.note_label.setObjectName("InsightMetricNote")
        self.note_label.setWordWrap(False)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.delta_label)
        layout.addWidget(self.note_label)

    def set_value(self, value, note=""):
        self.value_label.setText(value)
        self.note_label.setText(note)
        self.note_label.setVisible(bool(note))

    def set_delta(self, text, direction=None):
        """Show a comparison line such as "+18%" under the metric value.

        ``direction`` is "up", "down" or None and only affects colour, so
        the same data reads consistently across both themes. An empty text
        hides the line.
        """
        if not text:
            self.delta_label.setVisible(False)
            return

        object_name = {
            "up": "MetricDeltaPositive",
            "down": "MetricDeltaNegative",
        }.get(direction, "MetricDeltaNeutral")
        self.delta_label.setObjectName(object_name)
        self.delta_label.setText(text)
        self.delta_label.style().unpolish(self.delta_label)
        self.delta_label.style().polish(self.delta_label)
        self.delta_label.setVisible(True)


class PatternCard(QFrame):
    """Small pattern panel that consumes already-calculated pattern data.

    Accepts the same semantic ``tint``/``tone`` identity as MetricCard.
    """

    def __init__(self, title, tint=None, tone=None):
        super().__init__()
        self.setObjectName("InsightPattern")
        self.setMinimumHeight(98)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if tint:
            self.setProperty("tint", tint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("InsightMetricTitle")
        self.title_label = title_label
        self.value_label = QLabel("Not enough data yet")
        self.value_label.setObjectName("InsightPatternValue")
        if tone:
            self.value_label.setProperty("tone", tone)
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
        self.granularity = "daily"
        self.hovered_index = None
        self._draw_progress = 1.0
        self.anim = None
        # A fixed height keeps the chart compact and guarantees the painted
        # bars always fit inside their container at every window size.
        self.setFixedHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_points(self, points, granularity="daily"):
        self.points = tuple(points)
        self.granularity = granularity
        self.hovered_index = None
        self.setToolTip("")

        if is_reduced_motion_enabled():
            self._draw_progress = 1.0
            self.update()
            return

        if self.anim is not None and self.anim.state() == QVariantAnimation.Running:
            self.anim.stop()

        self._draw_progress = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(CHART_TREND_DURATION)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._on_draw_progress_changed)
        self.anim.start()

    def _on_draw_progress_changed(self, value):
        self._draw_progress = float(value)
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
        """Format exact, per-point hover copy from one calculated trend point."""
        return (
            f"{format_display_date(point.day, include_weekday=True)}\n"
            f"Focus time: {format_minutes(point.focus_minutes)}\n"
            f"Completed: {point.completed_tasks} of {point.total_tasks} planned"
        )

    def point_label(self, point):
        """Compact x-axis label appropriate to the chart granularity."""
        if self.granularity == "monthly":
            return point.day.strftime("%b")
        if self.granularity == "weekly":
            return point.day.strftime("%d %b")
        return point.day.strftime("%a")

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

        # Horizontal grid lines with compact axis captions. Four divisions
        # keep the scale readable without gridline noise.
        grid_font = painter.font()
        grid_font.setPointSizeF(7.5)
        painter.setFont(grid_font)
        divisions = 4
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

        # The strongest period is highlighted so high/low moments are
        # obvious at a glance; the rest keep the primary gradient.
        max_index = max(
            range(count),
            key=lambda index: (
                self.points[index].focus_minutes,
                -index,
            ),
        )
        show_value_labels = count <= 14

        for index, point in enumerate(self.points):
            x = chart_left + index * (bar_width + gap)
            if maximum > 0:
                base_h = max(3, (point.focus_minutes / maximum) * chart_height)
            else:
                base_h = 3
            height = max(3, base_h * self._draw_progress)
            y = chart_bottom - height
            is_hovered = index == self.hovered_index
            is_strongest = index == max_index

            painter.setPen(Qt.NoPen)
            if point.focus_minutes > 0:
                gradient = QLinearGradient(x, y, x, chart_bottom)
                if is_strongest:
                    top_color = QColor(
                        Colors.ACCENT
                        if not is_hovered
                        else Colors.ACCENT_HOVER
                    )
                    bottom_color = QColor(Colors.PRIMARY)
                else:
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

            # Value captions above the bars when the chart is not crowded.
            if show_value_labels and point.focus_minutes > 0:
                painter.setPen(
                    QColor(
                        Colors.TEXT_SECONDARY
                        if is_hovered or is_strongest
                        else Colors.TEXT_MUTED
                    )
                )
                painter.drawText(
                    int(x),
                    int(y) - 15,
                    max(1, int(bar_width)),
                    13,
                    Qt.AlignHCenter | Qt.AlignBottom,
                    self.value_label(point.focus_minutes),
                )

            if count == 1:
                label = "Today"
            elif count <= 7 or index == 0 or index == count - 1 or index % 5 == 0:
                label = self.point_label(point)
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

    @staticmethod
    def value_label(minutes):
        """Compact value caption used above sparse bars."""
        hours, remaining = divmod(max(0, int(minutes or 0)), 60)
        if hours > 0:
            return f"{hours}h {remaining}m" if remaining else f"{hours}h"
        return f"{remaining}m"


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


class ActivityDistributionChart(QWidget):
    """Ranked horizontal bars answering: where is my time actually going?

    Pure presentation: it receives already-computed (category, minutes,
    percent) shares and paints them in rank order. Bars are proportional
    to the largest category so relative magnitude is obvious at a glance.
    """

    ROW_HEIGHT = 32
    BAR_HEIGHT = 14
    PALETTE = (
        Colors.PRIMARY,
        Colors.ACCENT,
        Colors.SUCCESS,
        Colors.WARNING,
        Colors.PRIMARY_MUTED,
        Colors.ACCENT_SOFT,
        Colors.PRIMARY_PRESSED,
    )

    def __init__(self):
        super().__init__()
        self.items = ()
        self.total_minutes = 0
        self.hovered_index = None
        self._bar_progress = 1.0
        self.anim = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_items(self, items, total_minutes):
        self.items = tuple(items)
        self.total_minutes = max(0, int(total_minutes or 0))
        self.hovered_index = None
        self.setFixedHeight(
            max(1, len(self.items)) * self.ROW_HEIGHT + 8
        )

        if is_reduced_motion_enabled():
            self._bar_progress = 1.0
            self.update()
            return

        if self.anim is not None and self.anim.state() == QVariantAnimation.Running:
            self.anim.stop()

        self._bar_progress = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(CHART_BAR_DURATION)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._on_bar_progress_changed)
        self.anim.start()

    def _on_bar_progress_changed(self, value):
        self._bar_progress = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.items:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No focus time recorded yet.",
            )
            return

        maximum = max(minutes for _, minutes, _ in self.items)
        label_width = 150
        percent_width = 46
        bar_left = label_width + 14
        bar_right = self.width() - percent_width - 12

        for index, item in enumerate(self.items):
            category, minutes, percent = item
            row_top = 6 + index * self.ROW_HEIGHT
            center_y = row_top + self.ROW_HEIGHT // 2

            # Category label, truncated when long.
            font = painter.font()
            font.setPointSizeF(8.5)
            painter.setFont(font)
            painter.setPen(
                QColor(
                    Colors.TEXT_SECONDARY
                    if index == self.hovered_index
                    else Colors.TEXT_MUTED
                )
            )
            label = category
            if painter.fontMetrics().horizontalAdvance(label) > label_width - 8:
                while (
                    label
                    and painter.fontMetrics().horizontalAdvance(label + "…")
                    > label_width - 8
                ):
                    label = label[:-1]
                label += "…"
            painter.drawText(
                0,
                row_top,
                label_width,
                self.ROW_HEIGHT,
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )

            # Bar proportional to the strongest category.
            target_width = max(
                4,
                int((minutes / maximum) * (bar_right - bar_left)),
            )
            bar_width = max(4, int(target_width * self._bar_progress))
            bar_color = QColor(
                self.PALETTE[index % len(self.PALETTE)]
            )
            bar_rect = painter.fontMetrics().boundingRect("0").height()
            painter.setPen(Qt.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(
                bar_left,
                center_y - self.BAR_HEIGHT // 2,
                bar_width,
                self.BAR_HEIGHT,
                4,
                4,
            )

            # Minutes and share.
            painter.setPen(QColor(Colors.TEXT_SECONDARY))
            painter.drawText(
                bar_right + 2,
                row_top,
                self.width() - bar_right - 2,
                self.ROW_HEIGHT,
                Qt.AlignRight | Qt.AlignVCenter,
                format_minutes(minutes),
            )
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                bar_right - percent_width - 2,
                row_top,
                percent_width,
                self.ROW_HEIGHT,
                Qt.AlignRight | Qt.AlignVCenter,
                f"{percent}%",
            )

    def index_at_y(self, y_position):
        if not self.items:
            return None
        index = (int(y_position) - 6) // self.ROW_HEIGHT
        if 0 <= index < len(self.items):
            return index
        return None

    def mouseMoveEvent(self, event):
        index = self.index_at_y(event.position().y())
        if index != self.hovered_index:
            self.hovered_index = index
            self.update()
        if index is None:
            QToolTip.hideText()
            return super().mouseMoveEvent(event)

        category, minutes, percent = self.items[index]
        share_text = (
            f"{percent}% of focus time"
            if self.total_minutes > 0
            else "of focus time"
        )
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{category}\n{format_minutes(minutes)} · "
            f"{share_text}",
            self,
        )
        event.accept()

    def leaveEvent(self, event):
        self.hovered_index = None
        self.update()
        QToolTip.hideText()
        super().leaveEvent(event)


class DayHourHeatmap(QWidget):
    """Day-of-week x time-of-day focus heatmap.

    Rows are days of the week, columns are Morning / Afternoon / Evening /
    Night. Cell intensity reflects focus minutes, so a user can see their
    weekly rhythm at a glance. The interpretation ("strongest window") is
    computed by the service, never by this widget.
    """

    DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    BLOCK_LABELS = ("Morning", "Afternoon", "Evening", "Night")
    ROW_HEIGHT = 24
    HEADER_HEIGHT = 22
    LABEL_WIDTH = 40
    CELL_SPACING = 4

    def __init__(self):
        super().__init__()
        self.cells = {}
        self.max_minutes = 0
        self.total_sessions = 0
        self.setMouseTracking(True)
        self.hover_cell = None
        self.setFixedHeight(
            self.HEADER_HEIGHT
            + len(self.DAY_LABELS) * (self.ROW_HEIGHT + self.CELL_SPACING)
            + 6
        )

    def set_pattern(self, pattern):
        self.cells = {
            (cell.day_index, cell.block_index): (
                cell.focus_minutes,
                cell.session_count,
            )
            for cell in pattern.cells
        }
        self.max_minutes = max(
            (minutes for minutes, _ in self.cells.values()),
            default=0,
        )
        self.total_sessions = pattern.total_sessions
        self.hover_cell = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        chart_left = self.LABEL_WIDTH + 6
        chart_width = max(10, self.width() - chart_left - 4)
        column_width = chart_width / len(self.BLOCK_LABELS)

        font = painter.font()
        font.setPointSizeF(7.5)
        painter.setFont(font)

        # Column headers.
        for column, block in enumerate(self.BLOCK_LABELS):
            x = chart_left + column * column_width
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                int(x),
                4,
                int(column_width),
                self.HEADER_HEIGHT - 4,
                Qt.AlignHCenter | Qt.AlignVCenter,
                block,
            )

        # Row labels and cells.
        for row, day_label in enumerate(self.DAY_LABELS):
            y = self.HEADER_HEIGHT + row * (self.ROW_HEIGHT + self.CELL_SPACING)
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                0,
                int(y),
                self.LABEL_WIDTH - 4,
                self.ROW_HEIGHT,
                Qt.AlignRight | Qt.AlignVCenter,
                day_label,
            )

            for column in range(len(self.BLOCK_LABELS)):
                x = chart_left + column * column_width
                cell_rect = (
                    int(x) + 2,
                    int(y),
                    max(6, int(column_width) - 4),
                    self.ROW_HEIGHT,
                )
                minutes, count = self.cells.get((row, column), (0, 0))

                if minutes <= 0:
                    painter.setPen(QColor(Colors.BORDER))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(*cell_rect, 5, 5)
                    continue

                alpha = 40 + int(215 * (minutes / self.max_minutes))
                color = QColor(Colors.PRIMARY)
                color.setAlpha(alpha)
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(*cell_rect, 5, 5)

        if self.max_minutes <= 0:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                chart_left,
                self.HEADER_HEIGHT,
                max(10, self.width() - chart_left - 4),
                self.height() - self.HEADER_HEIGHT,
                Qt.AlignCenter,
                "No timestamped sessions yet.",
            )

    def cell_at(self, position):
        chart_left = self.LABEL_WIDTH + 6
        chart_width = max(10, self.width() - chart_left - 4)
        column_width = chart_width / len(self.BLOCK_LABELS)
        if position.x() < chart_left:
            return None
        column = int((position.x() - chart_left) // column_width)
        row = int(
            (position.y() - self.HEADER_HEIGHT)
            // (self.ROW_HEIGHT + self.CELL_SPACING)
        )
        if 0 <= row < len(self.DAY_LABELS) and 0 <= column < len(
            self.BLOCK_LABELS
        ):
            return row, column
        return None

    def mouseMoveEvent(self, event):
        cell = self.cell_at(event.position())
        if cell != self.hover_cell:
            self.hover_cell = cell
        if cell is None:
            QToolTip.hideText()
            return super().mouseMoveEvent(event)

        row, column = cell
        minutes, count = self.cells.get((row, column), (0, 0))
        if minutes <= 0:
            QToolTip.hideText()
            return super().mouseMoveEvent(event)

        session_text = "session" if count == 1 else "sessions"
        QToolTip.showText(
            event.globalPosition().toPoint(),
            (
                f"{self.DAY_LABELS[row]} {self.BLOCK_LABELS[column]}\n"
                f"{format_minutes(minutes)} focused · {count} {session_text}"
            ),
            self,
        )
        event.accept()

    def leaveEvent(self, event):
        self.hover_cell = None
        QToolTip.hideText()
        super().leaveEvent(event)


class LearnedInsightCard(QFrame):
    """One evidence-backed observation from "What Ascend Learned".

    The card shows WHAT (title + description), WHY (evidence line) and HOW
    STRONG the evidence is (confidence badge) in one glance. Styling is
    deliberately distinct (purple intelligence accent) but stays inside the
    shared design system.
    """

    CONFIDENCE_STYLES = {
        "high_confidence": (
            Colors.SUCCESS_SOFT,
            Colors.SUCCESS,
            Colors.SUCCESS_HOVER,
        ),
        "moderate_confidence": (
            Colors.ACCENT_SOFT,
            Colors.ACCENT_MUTED,
            Colors.ACCENT_HOVER,
        ),
        "early_signal": (
            Colors.WARNING_SOFT,
            Colors.WARNING,
            Colors.WARNING,
        ),
    }

    def __init__(self, insight):
        super().__init__()
        self.setObjectName("LearnedInsight")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)

        glyph = QLabel("◈")
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setFixedSize(24, 24)
        glyph.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 15px; font-weight: 800;"
        )

        title_label = QLabel(insight.title)
        title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 14px; font-weight: 750;"
        )

        badge = QLabel(evidence_label(insight.confidence))
        background, border, foreground = self.CONFIDENCE_STYLES.get(
            insight.confidence,
            (Colors.SURFACE_SECONDARY, Colors.BORDER, Colors.TEXT_MUTED),
        )
        badge.setStyleSheet(
            f"color: {foreground}; background-color: {background}; "
            f"border: 1px solid {border}; border-radius: {Radius.SM}px; "
            "padding: 2px 8px; font-size: 10px; font-weight: 700;"
        )

        header.addWidget(glyph)
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(badge)

        description = QLabel(insight.description)
        description.setWordWrap(True)
        description.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")

        evidence = QLabel(insight.evidence)
        evidence.setObjectName("InsightMetricNote")
        evidence.setWordWrap(True)

        layout.addLayout(header)
        layout.addWidget(description)
        layout.addWidget(evidence)


class AnalyticsWindow(QWidget):
    """Production Insights page rendered from a centralized data model."""

    def __init__(self, insights_service):
        super().__init__()
        self.insights_service = insights_service
        self.selected_range = "7_days"
        self.dashboard_data = None
        self.range_buttons = {}
        self.icon_factory = IconFactory(self)
        # Section title -> (icon label, qtawesome name). Icons are re-applied
        # on every refresh so they follow the active theme's colours.
        self.section_icon_labels = {}

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

        self.scroll_area = scroll_area

        # The page follows the narrative: how am I doing -> what happened ->
        # where does time go -> when do I work best -> patterns -> learned.
        self.content_layout.addLayout(self.create_header())
        sections = (
            self.create_overview_section(),
            self.create_focus_trends_section(),
            self.create_distribution_section(),
            self.create_day_hour_section(),
            self.create_calibration_section(),
            self.create_consistency_section(),
            self.create_learned_section(),
            self.create_highlights_section(),
            self.create_insights_section(),
        )
        for sec in sections:
            self.content_layout.addWidget(sec)
        self.content_layout.addStretch()

        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)

    def create_header(self):
        """Build the in-page hero and the shared range filter buttons.

        The range buttons are created here but displayed by the application
        shell's page header, so the page itself stays free of a second title.
        """
        layout = QHBoxLayout()
        layout.setSpacing(16)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        title = QLabel("Insights")
        title.setObjectName("Greeting")
        subtitle = QLabel("Understand your productivity. Improve it.")
        subtitle.setObjectName("MutedText")

        self.current_date_label = QLabel(format_display_date(date.today()))
        self.current_date_label.setObjectName("MutedText")

        self.range_caption_label = QLabel()
        self.range_caption_label.setObjectName("MutedText")

        self.range_group = QButtonGroup(self)
        for key, text in (
            ("today", "Today"),
            ("7_days", "7 Days"),
            ("30_days", "30 Days"),
            ("90_days", "3 Months"),
            ("all_time", "All Time"),
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

        caption_layout = QVBoxLayout()
        caption_layout.setSpacing(1)
        caption_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        caption_layout.addWidget(self.range_caption_label)
        caption_layout.addWidget(self.current_date_label, alignment=Qt.AlignRight)

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addLayout(caption_layout)
        return layout

    def create_overview_section(self):
        section, layout = self.create_section("Productivity Overview", "fa5s.tachometer-alt")
        self.overview_grid = QGridLayout()
        self.overview_grid.setContentsMargins(0, 0, 0, 0)
        self.overview_grid.setSpacing(10)
        # Semantic metric zones: focus = blue, completion = green,
        # activities = neutral, consistency = blue, streak = amber,
        # XP = purple.
        self.overview_cards = {
            "focus": MetricCard("Focus Time", tint="blue", tone="blue"),
            "completion": MetricCard("Completion", tint="green", tone="green"),
            "tasks": MetricCard("Activities"),
            "consistency": MetricCard("Consistency", tint="blue", tone="blue"),
            "streak": MetricCard("Current Streak", tint="amber", tone="amber"),
            "xp": MetricCard("XP Earned", tint="purple", tone="purple"),
        }
        for row in range(2):
            for column, key in enumerate(
                ("focus", "completion", "tasks")
                if row == 0
                else ("consistency", "streak", "xp")
            ):
                card = self.overview_cards[key]
                self.overview_grid.addWidget(card, row, column)
                self.overview_grid.setColumnStretch(column, 1)
        layout.addLayout(self.overview_grid)
        return section

    def create_focus_trends_section(self):
        section, layout = self.create_section("Focus Trends", "fa5s.bullseye")

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

    def create_distribution_section(self):
        section, layout = self.create_section("Where Your Time Goes", "fa5s.layer-group")
        self.distribution_chart = ActivityDistributionChart()
        self.distribution_total_label = QLabel()
        self.distribution_total_label.setObjectName("MutedText")
        layout.addWidget(self.distribution_chart)
        layout.addWidget(self.distribution_total_label)
        return section

    def create_day_hour_section(self):
        section, layout = self.create_section("When You Work Best", "fa5s.clock")
        self.day_hour_heatmap = DayHourHeatmap()
        self.rhythm_label = QLabel()
        self.rhythm_label.setObjectName("SectionTitle")
        self.rhythm_evidence_label = QLabel()
        self.rhythm_evidence_label.setObjectName("MutedText")
        layout.addWidget(self.day_hour_heatmap)
        layout.addWidget(self.rhythm_label)
        layout.addWidget(self.rhythm_evidence_label)
        return section

    def create_calibration_section(self):
        section, layout = self.create_section("Planning Accuracy", "fa5s.crosshairs")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.bias_card = PatternCard(
            "Estimate Bias", tint="blue", tone="blue"
        )
        self.typical_error_card = PatternCard(
            "Typical Error", tint="amber", tone="amber"
        )
        self.confidence_card = PatternCard(
            "Confidence", tint="purple", tone="purple"
        )
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
        section, layout = self.create_section("Consistency", "fa5s.calendar-check")
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

    def create_learned_section(self):
        section, layout = self.create_section("What Ascend Learned", "fa5s.brain")
        self.learned_layout = QVBoxLayout()
        self.learned_layout.setContentsMargins(0, 0, 0, 0)
        self.learned_layout.setSpacing(8)
        layout.addLayout(self.learned_layout)
        return section

    def create_highlights_section(self):
        section, layout = self.create_section("Personal Highlights", "fa5s.trophy")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.highlight_cards = {
            "best_day": MetricCard("Best Day", tint="blue", tone="blue"),
            "longest": MetricCard(
                "Longest Focus Session", tint="purple", tone="purple"
            ),
            "improvement": MetricCard(
                "Biggest Improvement", tint="green", tone="green"
            ),
        }
        for column, card in enumerate(self.highlight_cards.values()):
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        return section

    def create_insights_section(self):
        section, layout = self.create_section("Your Insights")
        self.insights_layout = QVBoxLayout()
        self.insights_layout.setContentsMargins(0, 0, 0, 0)
        self.insights_layout.setSpacing(8)
        layout.addLayout(self.insights_layout)
        return section

    def create_section(self, title, icon_name=None):
        """Build a titled Insights surface.

        ``icon_name`` optionally adds a small QtAwesome glyph beside the
        title. Icons stay subordinate to the information: muted by default,
        accent-tinted only for the intelligence section, and re-coloured on
        refresh so they follow the active theme.
        """
        section = QFrame()
        section.setObjectName("InsightSurface")
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")

        if icon_name:
            header = QHBoxLayout()
            header.setSpacing(8)
            icon_label = QLabel()
            icon_label.setFixedSize(18, 18)
            icon_label.setAlignment(Qt.AlignVCenter)
            self.section_icon_labels[title] = (icon_label, icon_name)
            header.addWidget(icon_label)
            header.addWidget(title_label)
            header.addStretch()
            layout.addLayout(header)
        else:
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
        self.refresh_section_icons()
        self.render_dashboard(self.dashboard_data)

    def refresh_section_icons(self):
        """Re-colour the section glyphs with the active theme's palette.

        Icons are muted supporting marks; the intelligence section
        ("What Ascend Learned") keeps a restrained purple accent so its
        identity survives the theme switch.
        """
        for title, (label, icon_name) in self.section_icon_labels.items():
            color = (
                Colors.ACCENT
                if title == "What Ascend Learned"
                else Colors.TEXT_MUTED
            )
            icon = self.icon_factory.get(icon_name, color)
            label.setPixmap(icon.pixmap(16, 16))

    def render_dashboard(self, data):
        self.range_caption_label.setText(
            comparison_caption(data.range_definition)
        )

        overview = data.overview
        self.overview_cards["focus"].set_value(
            format_minutes(overview.focus_minutes),
            data.range_definition.label,
        )
        self.overview_cards["focus"].set_delta(
            self.format_percent_delta(overview.focus_change_percent),
            self.delta_direction(overview.focus_change_percent),
        )

        self.overview_cards["tasks"].set_value(
            str(overview.completed_tasks),
            f"of {overview.total_tasks} planned",
        )
        self.overview_cards["tasks"].set_delta(
            self.format_count_delta(overview.activity_change),
            self.delta_direction(overview.activity_change),
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
        self.overview_cards["completion"].set_delta(
            self.format_points_delta(overview.completion_change_points),
            self.delta_direction(overview.completion_change_points),
        )

        self.overview_cards["consistency"].set_value(
            format_day_count(overview.active_days),
            "active days in this period",
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
        self.trend_chart.set_points(trend.points, trend.granularity)

        distribution = data.distribution
        self.distribution_chart.set_items(
            [
                (item.category, item.focus_minutes, item.percent)
                for item in distribution.items
            ],
            distribution.total_minutes,
        )
        if distribution.total_minutes > 0:
            self.distribution_total_label.setText(
                f"{format_minutes(distribution.total_minutes)} of focused "
                "work recorded in this period."
            )
        else:
            self.distribution_total_label.setText(
                "Complete a focus session to see where your time goes."
            )

        day_hour = data.day_hour
        self.day_hour_heatmap.set_pattern(day_hour)
        if day_hour.status == "ready" and day_hour.strongest_window_label:
            self.rhythm_label.setText(
                f"Your strongest focus window: "
                f"{day_hour.strongest_window_label}"
            )
            session_text = (
                "session" if day_hour.window_session_count == 1 else "sessions"
            )
            self.rhythm_evidence_label.setText(
                f"Based on {day_hour.window_session_count} {session_text} · "
                f"{format_minutes(day_hour.strongest_window_minutes)} focused"
            )
        elif day_hour.status == "empty":
            self.rhythm_label.setText("We're still learning your rhythm.")
            self.rhythm_evidence_label.setText(
                "Complete a few focus sessions to see when you work best."
            )
        else:
            self.rhythm_label.setText("We're still learning your rhythm.")
            self.rhythm_evidence_label.setText(
                f"{day_hour.total_sessions} sessions so far - more will "
                "reveal when you focus best."
            )

        self.render_highlights(data.highlights)
        self.render_learned(data.learned)

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

    @staticmethod
    def format_percent_delta(value):
        """"+18%", "-12%" or "" for an overview comparison value."""
        if value is None:
            return ""
        if value > 0:
            return f"+{value}%"
        return f"{value}%"

    @staticmethod
    def format_count_delta(value):
        """"+4", "-2" or "" for an activity-count comparison value."""
        if value is None:
            return ""
        return f"+{value}" if value > 0 else f"{value}"

    @staticmethod
    def format_points_delta(value):
        """"+7 pts", "-3 pts" or "" for a completion-rate change."""
        if value is None:
            return ""
        sign = "+" if value > 0 else ""
        return f"{sign}{value} pts"

    @staticmethod
    def delta_direction(value):
        """Map a comparison value to a semantic direction for colouring."""
        if value is None or value == 0:
            return None
        return "up" if value > 0 else "down"

    def render_highlights(self, highlights):
        """Render the Personal Highlights cards with honest fallbacks."""
        field_names = {
            "best_day": "best_day",
            "longest": "longest_session",
            "improvement": "improvement",
        }
        fallbacks = {
            "best_day": (
                "—",
                "Complete a focus session to find your best day.",
            ),
            "longest": (
                "—",
                "No focus sessions recorded in this period.",
            ),
            "improvement": (
                "—",
                "A comparison unlocks with previous-period data.",
            ),
        }
        for key, card in self.highlight_cards.items():
            highlight = getattr(highlights, field_names[key])
            if highlight is None:
                value, note = fallbacks[key]
                card.set_value(value, note)
            else:
                card.set_value(highlight.value, highlight.note)

    def render_learned(self, learned):
        """Render the "What Ascend Learned" cards.

        Empty states are deliberate: when no evidence-backed observation
        exists yet, the section says so instead of showing generic
        motivation.
        """
        self.clear_layout(self.learned_layout)

        if not learned:
            empty_card = QFrame()
            empty_card.setObjectName("LearnedInsight")
            empty_layout = QVBoxLayout(empty_card)
            empty_layout.setContentsMargins(16, 12, 16, 12)
            empty_layout.setSpacing(5)

            glyph = QLabel("◈")
            glyph.setStyleSheet(
                f"color: {Colors.ACCENT}; font-size: 15px; font-weight: 800;"
            )
            title = QLabel("Ascend hasn't learned this yet.")
            title.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 14px; font-weight: 750;"
            )
            description = QLabel(
                "More activity is needed to identify reliable patterns."
            )
            description.setWordWrap(True)
            description.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")

            empty_layout.addWidget(glyph)
            empty_layout.addWidget(title)
            empty_layout.addWidget(description)
            self.learned_layout.addWidget(empty_card)
            return

        for insight in learned:
            self.learned_layout.addWidget(LearnedInsightCard(insight))

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
            "warning": ("!", Colors.ERROR),
            "goal": ("•", Colors.PRIMARY),
            "pattern": ("◈", Colors.ACCENT),
            "streak": ("↑", Colors.WARNING),
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
