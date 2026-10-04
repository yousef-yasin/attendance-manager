"""Dashboard charts (QtCharts).

Both charts are single-series, so there is no legend box: the card title names
the series. Values are also available as text (tooltips, value labels, and
the Students/Sessions tables act as the table view).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QScatterSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip

from attendance_manager.domain.statistics import SessionStats
from attendance_manager.i18n import format_date, tr, trn
from attendance_manager.ui import theme


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(theme.FONT_FAMILY)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def _base_chart() -> QChart:
    chart = QChart()
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.legend().hide()
    chart.setMargins(QMargins(0, 6, 6, 0))
    chart.layout().setContentsMargins(0, 0, 0, 0)
    chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
    return chart


def _style_axis(axis, show_grid: bool) -> None:
    axis.setLabelsColor(QColor(theme.MUTED))
    axis.setLabelsFont(_font(8.5))
    axis.setLinePen(QPen(QColor("#C3C2B7"), 1))
    axis.setGridLineVisible(show_grid)
    axis.setGridLinePen(QPen(QColor(theme.GRID), 1))
    axis.setMinorGridLineVisible(False)


class _View(QChartView):
    def __init__(self, chart: QChart) -> None:
        super().__init__(chart)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(250)
        # Plots keep a left-to-right time/value axis in every language (the
        # convention in Arabic academic reporting); labels are localized.
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def _nice_step(raw: float) -> int:
    """Smallest 1/2/5 x 10^n step >= raw, so axis ticks land on round numbers."""
    step = 1
    while True:
        for factor in (1, 2, 5):
            if step * factor >= raw:
                return step * factor
        step *= 10


def distribution_label(index: int) -> str:
    """Localized name of attendance bucket ``index`` (see DISTRIBUTION_BUCKETS)."""
    return tr(f"distribution.bucket{index}")


def _short(text: str, limit: int = 12) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class TrendChart(_View):
    """Attendance % per session: 2px line, 8px markers, dashed at-risk reference."""

    def __init__(self) -> None:
        super().__init__(_base_chart())
        self._sessions: list[SessionStats] = []

    def set_data(self, sessions: Sequence[SessionStats], at_risk_below: float) -> None:
        chart = _base_chart()
        self._sessions = list(sessions)
        line = QLineSeries()
        pen = QPen(QColor(theme.ACCENT), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line.setPen(pen)
        dots = QScatterSeries()
        dots.setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeCircle)
        dots.setMarkerSize(10)
        dots.setColor(QColor(theme.ACCENT))
        dots.setBorderColor(QColor(theme.SURFACE))
        dots.setPen(QPen(QColor(theme.SURFACE), 2))
        reference = QLineSeries()
        ref_pen = QPen(QColor(theme.MUTED), 1, Qt.PenStyle.DashLine)
        reference.setPen(ref_pen)
        categories = []
        for i, s in enumerate(self._sessions):
            pct = s.percentage or 0.0
            line.append(QPointF(i, pct))
            dots.append(QPointF(i, pct))
            categories.append(
                f"#{s.session.session_number}\n{format_date(s.session.session_date, 'short')}"
            )
        if self._sessions:
            reference.append(QPointF(-0.5, at_risk_below))
            reference.append(QPointF(len(self._sessions) - 0.5, at_risk_below))
        for series in (reference, line, dots):
            chart.addSeries(series)
        x = QBarCategoryAxis()
        x.append(categories or [""])
        _style_axis(x, False)
        y = QValueAxis()
        y.setRange(0, 100)
        y.setTickCount(6)
        y.setLabelFormat("%d%%")
        _style_axis(y, True)
        y.setLineVisible(False)
        chart.addAxis(x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(y, Qt.AlignmentFlag.AlignLeft)
        for series in (reference, line, dots):
            series.attachAxis(x)
            series.attachAxis(y)
        dots.hovered.connect(self._on_hover)
        old = self.chart()
        self.setChart(chart)
        if old is not None:
            old.deleteLater()
        self.setToolTip(tr("charts.reference_tooltip", limit=f"{at_risk_below:g}"))

    def _on_hover(self, point: QPointF, state: bool) -> None:
        if not state:
            QToolTip.hideText()
            return
        index = round(point.x())
        if 0 <= index < len(self._sessions):
            s = self._sessions[index]
            pct = s.percentage or 0.0
            QToolTip.showText(
                QCursor.pos(),
                tr(
                    "charts.trend_tooltip",
                    session=s.session.label,
                    date=format_date(s.session.session_date),
                    percent=f"{pct:.1f}",
                    present=s.present,
                    absent=s.absent,
                ),
                self,
            )


class DistributionChart(_View):
    """How many students fall in each attendance range."""

    def __init__(self) -> None:
        super().__init__(_base_chart())
        self._data: list[tuple[str, int]] = []

    def set_data(self, distribution: Sequence[tuple[str, int]]) -> None:
        chart = _base_chart()
        self._data = list(distribution)
        bars = QBarSet(tr("charts.students_series"))
        bars.setColor(QColor(theme.ACCENT))
        bars.setBorderColor(QColor(theme.ACCENT))
        bars.setLabelColor(QColor(theme.INK_2))
        bars.setLabelFont(_font(8.5, True))
        for _, count in self._data:
            bars.append(count)
        series = QBarSeries()
        series.append(bars)
        series.setBarWidth(0.62)
        series.setLabelsVisible(True)
        series.setLabelsPosition(QBarSeries.LabelsPosition.LabelsOutsideEnd)
        series.setLabelsFormat("@value")
        chart.addSeries(series)
        x = QBarCategoryAxis()
        x.append([distribution_label(i) for i in range(len(self._data))])
        _style_axis(x, False)
        y = QValueAxis()
        top = max((c for _, c in self._data), default=0)
        step = _nice_step(top * 1.15 / 4)
        y.setRange(0, step * 4)
        y.setLabelFormat("%d")
        y.setTickCount(5)
        _style_axis(y, True)
        y.setLineVisible(False)
        chart.addAxis(x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(x)
        series.attachAxis(y)
        series.hovered.connect(self._on_hover)
        old = self.chart()
        self.setChart(chart)
        if old is not None:
            old.deleteLater()

    def _on_hover(self, status: bool, index: int, _bar: QBarSet) -> None:
        if status and 0 <= index < len(self._data):
            count = self._data[index][1]
            QToolTip.showText(
                QCursor.pos(),
                tr(
                    "charts.distribution_tooltip",
                    range=distribution_label(index),
                    students=trn("plural.students", count),
                ),
                self,
            )
        else:
            QToolTip.hideText()
