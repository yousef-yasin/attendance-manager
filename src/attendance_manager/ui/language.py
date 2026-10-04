"""Qt side of localization: layout direction, Qt's own strings, persistence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtWidgets import QApplication

from attendance_manager.i18n import DEFAULT_LANGUAGE, LANGUAGES, RTL_LANGUAGES, set_language, tr

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext

log = logging.getLogger(__name__)

SETTING_KEY = "language"
_qt_translators: list[QTranslator] = []


def load_language(ctx: AppContext) -> str:
    language = ctx.settings.get_value(SETTING_KEY, DEFAULT_LANGUAGE)
    return language if language in LANGUAGES else DEFAULT_LANGUAGE


def save_language(ctx: AppContext, language: str) -> None:
    ctx.settings.set_value(SETTING_KEY, language)


def apply_language(app: QApplication, language: str) -> None:
    """Switch the catalog, Qt's layout direction and Qt's built-in dialog strings."""
    set_language(language)
    rtl = language in RTL_LANGUAGES
    # Qt appends the display name to window titles ("Title - App"); keep it localized.
    app.setApplicationDisplayName(tr("app.name"))
    # Real RTL: Qt mirrors every layout, header, scroll bar and item view.
    app.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
    )
    # QLocale drives QDateEdit/QCalendarWidget/QSpinBox text. ar_EH is the CLDR Arabic
    # locale that uses Western digits (0-9) and the standard month names (يناير…),
    # keeping IDs, numbers and dates consistent across the whole interface.
    QLocale.setDefault(
        QLocale(QLocale.Language.Arabic, QLocale.Country.WesternSahara)
        if rtl
        else QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    )
    for translator in _qt_translators:
        app.removeTranslator(translator)
    _qt_translators.clear()
    if language != "en":
        path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for name in ("qtbase", "qt"):
            translator = QTranslator(app)
            if translator.load(f"{name}_{language}", path):
                app.installTranslator(translator)
                _qt_translators.append(translator)
                break
        else:
            log.info("Qt translations for %s not found in %s", language, path)
