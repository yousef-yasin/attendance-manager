"""Table models, filtering proxy and painting delegates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QRectF,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from attendance_manager.domain.models import StudentStanding
from attendance_manager.i18n import bidi_value, tr
from attendance_manager.ui import theme

SORT_ROLE = Qt.ItemDataRole.UserRole
PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 3

_Index = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True)
class Column:
    title: str
    value: Callable[[Any], Any]
    display: Callable[[Any], str] | None = None
    align: str = "left"  # left | right | center
    kind: str = "text"  # text | chip | percent | status
    width: int | None = None
    tooltip: Callable[[Any], str] | None = None


class ObjectTableModel(QAbstractTableModel):
    """Rows are arbitrary objects; columns describe how to show them."""

    def __init__(
        self, columns: Sequence[Column], rows: Sequence[Any] = (), parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.columns = list(columns)
        self.rows = list(rows)

    def set_rows(self, rows: Sequence[Any], columns: Sequence[Column] | None = None) -> None:
        self.beginResetModel()
        if columns is not None:
            self.columns = list(columns)
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.columns)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.columns):
            col = self.columns[section]
            if role == Qt.ItemDataRole.DisplayRole:
                return col.title
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return _alignment(col.align)
        return None

    @staticmethod
    def _display(row: Any, col: Column) -> str:
        if col.display is not None:
            return col.display(row)
        value = col.value(row)
        if value is None:
            return "—"
        if isinstance(value, StudentStanding):
            return tr(f"standing.{value.name.lower()}")
        return str(value)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            # Data such as "11.xls" must not be reordered by an RTL paragraph.
            return bidi_value(self._display(row, col))
        if role == SORT_ROLE:
            value = col.value(row)
            if isinstance(value, StudentStanding):
                return list(StudentStanding).index(value)
            if value is None:
                return -1.0 if col.kind == "percent" else ""
            if isinstance(value, str):
                return value.casefold()
            return value
        if role == PAYLOAD_ROLE:
            return row
        if role == KIND_ROLE:
            return col.kind
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(col.align)
        if role == Qt.ItemDataRole.ToolTipRole and col.tooltip is not None:
            return col.tooltip(row)
        if role == Qt.ItemDataRole.UserRole + 10:  # raw value for delegates
            return col.value(row)
        return None


def mapping_column(name: str, source: Callable[[Any], Mapping[str, str]]) -> Column:
    """A column showing ``source(row)[name]`` (e.g. one master-file field)."""
    return Column(name, lambda row: source(row).get(name, ""))


def _alignment(align: str) -> Qt.AlignmentFlag:
    horizontal = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "right": Qt.AlignmentFlag.AlignRight,
        "center": Qt.AlignmentFlag.AlignHCenter,
    }[align]
    return horizontal | Qt.AlignmentFlag.AlignVCenter


class SearchFilterProxy(QSortFilterProxyModel):
    """Case-insensitive search over all columns plus an optional predicate."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._needle = ""
        self._predicate: Callable[[Any], bool] | None = None
        self.setSortRole(SORT_ROLE)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search(self, text: str) -> None:
        self._refilter(lambda: setattr(self, "_needle", " ".join(text.casefold().split())))

    def set_predicate(self, predicate: Callable[[Any], bool] | None) -> None:
        self._refilter(lambda: setattr(self, "_predicate", predicate))

    def _refilter(self, change: Callable[[], None]) -> None:
        # Qt >= 6.10 replaces invalidateFilter() with begin/endFilterChange().
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            change()
            self.endFilterChange()
        else:  # pragma: no cover - older Qt
            change()
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        if self._predicate is not None:
            payload = model.data(model.index(source_row, 0, source_parent), PAYLOAD_ROLE)
            if not self._predicate(payload):
                return False
        if not self._needle:
            return True
        haystack = " ".join(
            str(
                model.data(model.index(source_row, c, source_parent), Qt.ItemDataRole.DisplayRole)
                or ""
            )
            for c in range(model.columnCount())
        ).casefold()
        return all(part in haystack for part in self._needle.split())

    def lessThan(self, left: _Index, right: _Index) -> bool:
        a = left.data(SORT_ROLE)
        b = right.data(SORT_ROLE)
        try:
            return bool(a < b)
        except TypeError:
            return str(a) < str(b)


class ChipDelegate(QStyledItemDelegate):
    """Paints standing / attendance status as a pill with a dot and label."""

    # Keyed by the column's semantic value, never by (translated) display text.
    COLORS = {
        "present": (theme.GOOD, theme.GOOD_SOFT),
        "absent": (theme.CRITICAL, theme.CRITICAL_SOFT),
        "not_enrolled": (theme.MUTED, theme.NEUTRAL_SOFT),
        "active": (theme.GOOD, theme.GOOD_SOFT),
        "removed": (theme.MUTED, theme.NEUTRAL_SOFT),
        "archived": (theme.MUTED, theme.NEUTRAL_SOFT),
    }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        self._paint_background(painter, option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text or text == "—":
            return
        raw = index.data(Qt.ItemDataRole.UserRole + 10)
        if isinstance(raw, StudentStanding):
            dot, soft = theme.STANDING_COLORS[raw]
        else:
            dot, soft = self.COLORS.get(str(raw), (theme.MUTED, theme.NEUTRAL_SOFT))
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(option.font)
        font.setPointSizeF(max(8.0, font.pointSizeF() - 0.8))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 32
        rect = option.rect
        left = rect.right() - 8 - width if rtl else rect.x() + 8
        pill = QRectF(left, rect.center().y() - 11, width, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(soft))
        painter.drawRoundedRect(pill, 11, 11)
        painter.setBrush(QColor(dot))
        dot_x = pill.right() - 18 if rtl else pill.x() + 10
        painter.drawEllipse(QRectF(dot_x, pill.center().y() - 4, 8, 8))
        painter.setPen(QColor(theme.INK))
        text_rect = pill.adjusted(8, 0, -24, 0) if rtl else pill.adjusted(24, 0, -8, 0)
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, text
        )
        painter.restore()

    @staticmethod
    def _paint_background(painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        opt = QStyleOptionViewItem(option)
        QStyledItemDelegate().initStyleOption(opt, index)
        opt.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)


class PercentDelegate(QStyledItemDelegate):
    """Percentage text with a slim bar; bar color follows the threshold band."""

    def __init__(
        self, thresholds_getter: Callable[[], tuple[float, float]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._thresholds = thresholds_getter

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        ChipDelegate._paint_background(painter, option, index)
        value = index.data(Qt.ItemDataRole.UserRole + 10)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect: QRect = option.rect.adjusted(10, 0, -10, 0)
        if value is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "—")
            painter.restore()
            return
        at_risk, warning = self._thresholds()
        color = (
            theme.CRITICAL if value < at_risk else theme.WARNING if value < warning else theme.GOOD
        )
        text = f"{value:.1f}%"
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        text_width = 56
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        painter.setPen(QColor(theme.INK))
        # The number sits on the leading side; the bar grows away from it.
        text_x = rect.right() - text_width if rtl else rect.x()
        painter.drawText(
            QRect(text_x, rect.y(), text_width, rect.height()),
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignAbsolute
            | (Qt.AlignmentFlag.AlignLeft if rtl else Qt.AlignmentFlag.AlignRight),
            text,
        )
        bar_w = max(24, rect.width() - text_width - 10)
        bar_x = rect.x() if rtl else rect.x() + text_width + 10
        track = QRectF(bar_x, rect.center().y() - 3, bar_w, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.NEUTRAL_SOFT))
        painter.drawRoundedRect(track, 3, 3)
        fill_w = track.width() * max(0.0, min(1.0, value / 100.0))
        fill_x = track.right() - fill_w if rtl else track.x()
        fill = QRectF(fill_x, track.y(), fill_w, 6)
        painter.setBrush(QColor(color))
        if fill.width() > 0:
            painter.drawRoundedRect(fill, 3, 3)
        painter.restore()


def configure_table(
    view: QTableView, row_height: int = 40, stretch_column: int | None = None
) -> None:
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setAlternatingRowColors(False)
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.setMouseTracking(True)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(row_height)
    view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    header = view.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setMinimumSectionSize(60)
    header.setStretchLastSection(stretch_column is None)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setTabKeyNavigation(False)


def apply_column_widths(
    view: QTableView, columns: Sequence[Column], stretch_title: str | None = None
) -> None:
    header = view.horizontalHeader()
    for i, col in enumerate(columns):
        if stretch_title is not None and col.title == stretch_title:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            continue
        header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        if col.width:
            view.setColumnWidth(i, col.width)
        else:
            view.resizeColumnToContents(i)
            view.setColumnWidth(i, min(max(view.columnWidth(i) + 16, 90), 320))


def install_delegates(
    view: QTableView, columns: Sequence[Column], percent: PercentDelegate, chip: ChipDelegate
) -> None:
    plain = view.itemDelegate()
    count = max(len(columns), view.model().columnCount() if view.model() else 0)
    for i in range(count):
        kind = columns[i].kind if i < len(columns) else "text"
        view.setItemDelegateForColumn(
            i, percent if kind == "percent" else chip if kind == "chip" else plain
        )
