"""Segmented [ العربية | English ] language control for the header."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

from attendance_manager.i18n import LANGUAGES, tr
from attendance_manager.ui import theme


class LanguageSwitch(QFrame):
    language_selected = Signal(str)

    # Arabic first, as requested: [ العربية | English ]
    ORDER = ("ar", "en")

    def __init__(self, current: str) -> None:
        super().__init__()
        self.setObjectName("LanguageSwitch")
        self.setToolTip(tr("topbar.language_tooltip"))
        self.setStyleSheet(
            f"#LanguageSwitch {{ background: {theme.NEUTRAL_SOFT}; border: 1px solid {theme.BORDER};"
            " border-radius: 10px; }"
            "#LanguageSwitch QPushButton { border: none; border-radius: 7px; padding: 5px 12px;"
            f" background: transparent; color: {theme.INK_2}; font-size: 12.5px; min-height: 18px; }}"
            f"#LanguageSwitch QPushButton:hover {{ color: {theme.INK}; }}"
            f"#LanguageSwitch QPushButton:checked {{ background: {theme.SURFACE}; color: {theme.INK};"
            " font-weight: 600; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for code in self.ORDER:
            # Language names are shown in their own script (endonyms), never translated.
            b = QPushButton(LANGUAGES[code])
            b.setCheckable(True)
            b.setChecked(code == current)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAccessibleName(LANGUAGES[code])
            # "toggled" (not "clicked") so keyboard, mouse *and* assistive technology
            # (screen readers / UI Automation toggle the button) all switch language.
            b.toggled.connect(lambda checked, c=code: self._toggled(c, checked))
            self._group.addButton(b)
            self.buttons[code] = b
            row.addWidget(b)

    def _toggled(self, code: str, checked: bool) -> None:
        if checked:
            self.language_selected.emit(code)
