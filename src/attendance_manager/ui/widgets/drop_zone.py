from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout, QWidget

from attendance_manager.i18n import tr
from attendance_manager.importing.reader import SUPPORTED_EXTENSIONS
from attendance_manager.ui import theme
from attendance_manager.ui.icons import pixmap
from attendance_manager.ui.widgets.common import button, label


def spreadsheet_from_mime(event: QDragEnterEvent | QDropEvent) -> Path | None:
    mime = event.mimeData()
    if not mime.hasUrls():
        return None
    for url in mime.urls():
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                return path
    return None


class DropZone(QFrame):
    """Big friendly target: drop an Excel file or click Browse."""

    file_selected = Signal(Path)

    def __init__(
        self,
        title: str,
        hint: str,
        dialog_title: str,
        start_dir: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(220)
        self._dialog_title = dialog_title
        self.start_dir = start_dir
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(8)
        layout.addStretch(1)
        badge = QLabel()
        badge.setFixedSize(60, 60)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap("upload", theme.ACCENT, 26))
        badge.setStyleSheet(f"background: {theme.ACCENT_SOFT}; border-radius: 30px; border: none;")
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        t = label(title, "DropTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t)
        h = label(hint, "Secondary", wrap=True)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(h)
        browse = button(tr("dropzone.browse"), "primary", "folder", self.browse)
        browse.setDefault(True)
        layout.addSpacing(6)
        layout.addWidget(browse, 0, Qt.AlignmentFlag.AlignHCenter)
        formats = label(tr("dropzone.supported"), "Muted")
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(formats)
        layout.addStretch(1)
        self.browse_button = browse

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._dialog_title, self.start_dir, tr("files.spreadsheet_filter")
        )
        if path:
            self.start_dir = str(Path(path).parent)
            self.file_selected.emit(Path(path))

    def _set_hover(self, hover: bool) -> None:
        self.setProperty("hover", "true" if hover else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if spreadsheet_from_mime(event):
            event.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_hover(False)
        path = spreadsheet_from_mime(event)
        if path:
            event.acceptProposedAction()
            self.file_selected.emit(path)
