"""Reusable building blocks: cards, stat tiles, banners, empty states, buttons."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.models import StudentStanding
from attendance_manager.i18n import bidi_value, is_rtl, paragraph, tr
from attendance_manager.ui import theme
from attendance_manager.ui.icons import icon, pixmap


def button(
    text: str,
    kind: str = "",
    icon_name: str | None = None,
    on_click: Callable[[], object] | None = None,
    tooltip: str = "",
) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    if icon_name:
        color = (
            "#FFFFFF"
            if kind in ("primary", "danger")
            else (theme.ACCENT if kind == "ghost" else theme.INK_2)
        )
        btn.setIcon(icon(icon_name, color))
        btn.setIconSize(QSize(16, 16))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        btn.setToolTip(tooltip)
    if on_click is not None:
        btn.clicked.connect(lambda _=False: on_click())
    return btn


def label(
    text: str = "", object_name: str = "", wrap: bool = False, selectable: bool = False
) -> QLabel:
    lbl = QLabel(text)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def icon_label(name: str, color: str, size: int = 18) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(pixmap(name, color, size))
    lbl.setFixedSize(size, size)
    return lbl


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            break
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                clear_layout(child)


class Card(QFrame):
    def __init__(
        self, parent: QWidget | None = None, padding: int = 18, shadow: bool = True
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(10)
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(18)
            effect.setOffset(0, 2)
            effect.setColor(QColor(16, 27, 45, 18))
            self.setGraphicsEffect(effect)

    def add_header(self, title: str, subtitle: str = "", trailing: QWidget | None = None) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(title, "CardTitle"))
        if subtitle:
            texts.addWidget(label(subtitle, "CardSubtitle", wrap=True))
        row.addLayout(texts, 1)
        if trailing is not None:
            row.addWidget(trailing, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(row)


class StatCard(Card):
    """KPI tile: label, big value, hint. Optional accent icon."""

    clicked = Signal()

    def __init__(
        self, title: str, icon_name: str, accent: str = theme.ACCENT, small: bool = False
    ) -> None:
        super().__init__(padding=16)
        self.setMinimumHeight(104 if not small else 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top = QHBoxLayout()
        top.setSpacing(8)
        badge = QLabel()
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap(icon_name, accent, 16))
        tint = QColor(accent)
        badge.setStyleSheet(
            f"background: rgba({tint.red()},{tint.green()},{tint.blue()},28); border-radius: 8px;"
        )
        self.title_label = label(title, "StatLabel")
        top.addWidget(badge)
        top.addWidget(self.title_label, 1)
        self.body.addLayout(top)
        self.value_label = label("—", "StatValueSmall" if small else "StatValue")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_label = label("", "StatHint", wrap=True)
        self.body.addWidget(self.value_label)
        self.body.addWidget(self.hint_label)
        self.body.addStretch(1)

    def set_value(self, value: str, hint: str = "", tooltip: str = "") -> None:
        self.value_label.setText(value)
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))
        self.setToolTip(tooltip)

    def mouseReleaseEvent(self, event) -> None:
        self.clicked.emit()
        super().mouseReleaseEvent(event)


class ResponsiveGrid(QWidget):
    """Lays out child widgets in as many columns as fit (min width per item)."""

    def __init__(self, min_item_width: int = 220, max_columns: int = 6, spacing: int = 14) -> None:
        super().__init__()
        self._items: list[QWidget] = []
        self._min = min_item_width
        self._max = max_columns
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)

    def set_items(self, widgets: Sequence[QWidget]) -> None:
        for w in self._items:
            self._grid.removeWidget(w)
            w.setParent(None)
        self._items = list(widgets)
        for w in self._items:
            # An explicit minimum stops long text from forcing the grid wider than the
            # window; the column count below guarantees each item gets at least this.
            w.setMinimumWidth(int(self._min * 0.8))
            w.setSizePolicy(QSizePolicy.Policy.Ignored, w.sizePolicy().verticalPolicy())
        self._columns = 0
        self._relayout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        width = max(self.width(), 1)
        spacing = self._grid.spacing()
        columns = max(
            1, min(self._max, (width + spacing) // (self._min + spacing), len(self._items) or 1)
        )
        if columns == self._columns and all(w.parent() is self for w in self._items):
            return
        self._columns = columns
        for w in self._items:
            self._grid.removeWidget(w)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)
        for index, w in enumerate(self._items):
            self._grid.addWidget(w, index // columns, index % columns)
            w.show()
        for c in range(columns):
            self._grid.setColumnStretch(c, 1)


class EmptyState(QWidget):
    def __init__(
        self, icon_name: str, title: str, text: str, actions: Sequence[QPushButton] = ()
    ) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(10)
        layout.addStretch(1)
        badge = QLabel()
        badge.setFixedSize(72, 72)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap(icon_name, theme.ACCENT, 32, 1.75))
        badge.setStyleSheet(f"background: {theme.ACCENT_SOFT}; border-radius: 36px;")
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(6)
        t = label(title, "EmptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t)
        self.title_label = t
        body = label("", "EmptyText", wrap=True)
        self.body_label = body
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setFixedWidth(520)
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        self.set_text(text)
        if actions:
            row = QHBoxLayout()
            row.addStretch(1)
            for a in actions:
                row.addWidget(a)
            row.addStretch(1)
            layout.addSpacing(8)
            layout.addLayout(row)
        layout.addStretch(2)

    def set_text(self, text: str) -> None:
        # An aligned, word-wrapped label does not get height-for-width from the
        # layout, so reserve the wrapped height explicitly.
        self.body_label.setText(text)
        self.body_label.setFixedHeight(self.body_label.heightForWidth(520) + 4 if text else 0)


_SEVERITY_ICON = {
    "danger": ("alert", theme.CRITICAL_TEXT),
    "warning": ("alert", theme.WARNING_TEXT),
    "info": ("info", theme.ACCENT),
    "success": ("check", theme.GOOD_TEXT),
}


class Banner(QFrame):
    def __init__(self, severity: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setProperty("severity", severity)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        name, color = _SEVERITY_ICON.get(severity, _SEVERITY_ICON["info"])
        row.addWidget(icon_label(name, color, 16), 0, Qt.AlignmentFlag.AlignTop)
        self.text = label(paragraph(text), wrap=True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.text, 1)


def standing_label(standing: StudentStanding) -> str:
    return tr(f"standing.{standing.name.lower()}")


class StatusChip(QLabel):
    """A pill with a colored dot and a text label (never color alone)."""

    def __init__(
        self, standing: StudentStanding | None = None, text: str = "", dot: str = "", soft: str = ""
    ) -> None:
        super().__init__()
        self._dot = QColor(theme.MUTED)
        # Room for the dot on the leading side (right side in RTL).
        if is_rtl():
            self.setContentsMargins(10, 3, 22, 3)
        else:
            self.setContentsMargins(22, 3, 10, 3)
        if standing is not None:
            self.set_standing(standing)
        elif text:
            self.set_custom(text, dot or theme.MUTED, soft or theme.NEUTRAL_SOFT)

    def set_standing(self, standing: StudentStanding) -> None:
        dot, soft = theme.STANDING_COLORS[standing]
        self.set_custom(standing_label(standing), dot, soft)

    def set_custom(self, text: str, dot: str, soft: str) -> None:
        self._dot = QColor(dot)
        self.setText(text)
        self.setStyleSheet(
            f"background: {soft}; border-radius: 11px; font-size: 12px; font-weight: 600;"
        )
        self.setFixedHeight(22)
        self.adjustSize()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._dot)
        x = self.width() - 18 if is_rtl() else 10
        painter.drawEllipse(x, self.height() // 2 - 4, 8, 8)
        painter.end()


class Separator(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {theme.BORDER}; border: none;")


class InfoGrid(QWidget):
    """Two-column key/value grid used for student and session details."""

    def __init__(self, pairs: Sequence[tuple[str, str]], columns: int = 2) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(10)
        for index, (key, value) in enumerate(pairs):
            row, col = divmod(index, columns)
            box = QVBoxLayout()
            box.setSpacing(1)
            box.addWidget(label(key, "InfoKey"))
            v = label(paragraph(bidi_value(value or "—")), "InfoValue", wrap=True, selectable=True)
            box.addWidget(v)
            grid.addLayout(box, row, col)
        for c in range(columns):
            grid.setColumnStretch(c, 1)
