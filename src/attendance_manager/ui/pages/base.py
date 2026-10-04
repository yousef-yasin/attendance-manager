from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from attendance_manager.i18n import paragraph, tr
from attendance_manager.ui import theme
from attendance_manager.ui.icons import directional, pixmap

if TYPE_CHECKING:
    from attendance_manager.ui.main_window import MainWindow

log = logging.getLogger(__name__)


class Page(QWidget):
    """A navigable page. Refreshes lazily: only when visible and data changed."""

    key = ""
    needs_course = False

    @property
    def title(self) -> str:
        return tr(f"pages.{self.key}.title")

    @property
    def subtitle(self) -> str:
        return tr(f"pages.{self.key}.subtitle")

    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window_ = window
        self.ctx = window.ctx
        self.state = window.state
        self._dirty = True

    def header_subtitle(self) -> str:
        return self.subtitle

    def mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh_now()

    def refresh_now(self) -> None:
        self._dirty = False
        try:
            self.refresh()
        except Exception:
            log.exception("Refreshing page %s failed", self.key)
            self.window_.toast(
                "error",
                tr("errors.page_refresh_title"),
                tr("errors.page_refresh_detail"),
            )

    def refresh(self) -> None:  # pragma: no cover - overridden
        pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self.refresh_now()


def scroll_container(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


def page_body(margins: tuple[int, int, int, int] = (28, 8, 28, 28)) -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*margins)
    layout.setSpacing(16)
    return widget, layout


class ListRow(QFrame):
    """A clickable row used in dashboard lists."""

    def __init__(self, title: str, subtitle: str, trailing: QWidget | None, on_click=None) -> None:
        super().__init__()
        self.setObjectName("ListRow")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if on_click else Qt.CursorShape.ArrowCursor
        )
        self.setStyleSheet(
            f"#ListRow {{ border-radius: 8px; }} #ListRow:hover {{ background: {theme.SURFACE_ALT}; }}"
        )
        self._on_click = on_click
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        t = QLabel(paragraph(title))
        t.setStyleSheet("font-size: 13px; font-weight: 600;")
        s = QLabel(paragraph(subtitle))
        s.setStyleSheet(f"font-size: 11.5px; color: {theme.MUTED};")
        texts.addWidget(t)
        texts.addWidget(s)
        row.addLayout(texts, 1)
        if trailing is not None:
            row.addWidget(trailing)
        if on_click:
            chevron = QLabel()
            chevron.setPixmap(pixmap(directional("chevron-right"), theme.MUTED, 14))
            row.addWidget(chevron)

    def mouseReleaseEvent(self, event) -> None:
        if self._on_click and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mouseReleaseEvent(event)
