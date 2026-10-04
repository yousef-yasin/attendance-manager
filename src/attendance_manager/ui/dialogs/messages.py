"""Error display and confirmation dialogs (plain-language, instructor friendly)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.errors import AttendanceError
from attendance_manager.i18n import tr
from attendance_manager.ui import theme
from attendance_manager.ui.icons import pixmap
from attendance_manager.ui.widgets.common import button, label

log = logging.getLogger(__name__)


def show_error(parent: QWidget | None, exc: BaseException, title: str | None = None) -> None:
    title = title or tr("errors.title.generic")
    if isinstance(exc, AttendanceError):
        text = exc.message
        details = exc.details
    else:
        log.error("Unexpected error", exc_info=exc)
        text = tr("errors.unexpected")
        details = f"{type(exc).__name__}: {exc}"
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    if details:
        box.setDetailedText(details)
    box.exec()


class ConfirmDialog(QDialog):
    """Explicit confirmation; optionally requires typing a phrase for destructive actions."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        confirm_text: str,
        danger: bool = False,
        type_to_confirm: str | None = None,
        details: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        head = QHBoxLayout()
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color, soft = (
            (theme.CRITICAL, theme.CRITICAL_SOFT) if danger else (theme.ACCENT, theme.ACCENT_SOFT)
        )
        badge.setPixmap(pixmap("alert" if danger else "info", color, 20))
        badge.setStyleSheet(f"background: {soft}; border-radius: 20px;")
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.addWidget(label(title, "SectionTitle"))
        body = label(message, wrap=True)
        body.setMinimumWidth(360)
        texts.addWidget(body)
        if details:
            texts.addWidget(label(details, "Secondary", wrap=True))
        head.addLayout(texts, 1)
        layout.addLayout(head)
        self._phrase = type_to_confirm
        self.input: QLineEdit | None = None
        if type_to_confirm:
            layout.addWidget(
                label(
                    tr("confirm.type_to_confirm", phrase=type_to_confirm), "FieldLabel", wrap=True
                )
            )
            self.input = QLineEdit()
            self.input.setPlaceholderText(type_to_confirm)
            self.input.textChanged.connect(self._update)
            layout.addWidget(self.input)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = button(tr("actions.cancel"), on_click=self.reject)
        self.ok = button(confirm_text, "danger" if danger else "primary", on_click=self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.ok)
        layout.addLayout(buttons)
        cancel.setDefault(True)
        cancel.setFocus()
        self._update()

    def _update(self) -> None:
        if self._phrase and self.input is not None:
            self.ok.setEnabled(
                self.input.text().strip().casefold() == self._phrase.strip().casefold()
            )


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    confirm_text: str,
    danger: bool = False,
    type_to_confirm: str | None = None,
    details: str = "",
) -> bool:
    dialog = ConfirmDialog(parent, title, message, confirm_text, danger, type_to_confirm, details)
    return dialog.exec() == QDialog.DialogCode.Accepted
