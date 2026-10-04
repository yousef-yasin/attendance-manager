"""Centralized localization.

All user-facing text lives in ``attendance_manager/locales/<lang>.json`` under
stable dotted keys (``nav.dashboard``, ``errors.file_empty`` …). Code calls:

* ``tr(<key>, name=value)`` — a translated string with ``{name}`` placeholders;
* ``trn(<key>, count, …)`` — plural-aware (CLDR rules; Arabic has six forms);
* ``format_date(date, style)`` — localized month/day names, Western digits.

This module is pure Python (no Qt), so services, importers and the report
writer use the same catalog as the UI. The Qt side (layout direction, Qt's
own dialog strings) is handled by ``attendance_manager.ui.language``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
LANGUAGES: dict[str, str] = {"en": "English", "ar": "العربية"}
RTL_LANGUAGES = frozenset({"ar"})

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


def locales_dir() -> Path:
    from attendance_manager.paths import resource_path

    bundled = resource_path("locales")
    return bundled if bundled.exists() else _LOCALES_DIR


def _flatten(prefix: str, node: Any, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten(f"{prefix}.{key}" if prefix else key, value, out)
    else:
        out[prefix] = node


@cache
def load_catalog(language: str) -> dict[str, Any]:
    """Flattened ``{dotted.key: text}`` for a language."""
    path = locales_dir() / f"{language}.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    flat: dict[str, Any] = {}
    _flatten("", data, flat)
    return flat


def plural_category(language: str, count: int) -> str:
    n = abs(int(count))
    if language == "ar":
        if n == 0:
            return "zero"
        if n == 1:
            return "one"
        if n == 2:
            return "two"
        if 3 <= n % 100 <= 10:
            return "few"
        if 11 <= n % 100 <= 99:
            return "many"
        return "other"
    return "one" if n == 1 else "other"


class Translator:
    def __init__(self) -> None:
        self.language = DEFAULT_LANGUAGE
        self._listeners: list[Callable[[str], None]] = []

    # ------------------------------------------------------------ language
    def set_language(self, language: str) -> None:
        if language not in LANGUAGES:
            log.warning("Unsupported language %r; using English", language)
            language = DEFAULT_LANGUAGE
        if language == self.language:
            return
        self.language = language
        for listener in list(self._listeners):
            listener(language)

    def add_listener(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def is_rtl(self) -> bool:
        return self.language in RTL_LANGUAGES

    # -------------------------------------------------------------- lookup
    def raw(self, key: str) -> Any:
        for language in (self.language, DEFAULT_LANGUAGE):
            catalog = load_catalog(language)
            if key in catalog:
                return catalog[key]
        log.error("Missing translation key %r", key)
        return key

    def tr(self, key: str, **values: Any) -> str:
        text = self.raw(key)
        if not isinstance(text, str):
            return key
        if values:
            try:
                return text.format(**self._bidi_values(values))
            except (KeyError, IndexError, ValueError):
                log.error("Bad placeholders for %r (%s)", key, self.language)
                return text
        return text

    def trn(self, key: str, count: int, **values: Any) -> str:
        category = plural_category(self.language, count)
        catalog = load_catalog(self.language)
        for candidate in (f"{key}.{category}", f"{key}.other"):
            if candidate in catalog:
                return self._format(catalog[candidate], count=count, **values)
        english = load_catalog(DEFAULT_LANGUAGE)
        fallback = english.get(f"{key}.{plural_category('en', count)}") or english.get(
            f"{key}.other", key
        )
        return self._format(fallback, count=count, **values)

    def _format(self, text: str, **values: Any) -> str:
        try:
            return text.format(**self._bidi_values(values))
        except (KeyError, IndexError, ValueError):
            return text

    def _bidi_values(self, values: dict[str, Any]) -> dict[str, Any]:
        """Keep left-to-right data (file names, e-mails, paths) intact inside RTL text."""
        if not self.is_rtl:
            return values
        return {k: bidi_value(v) if isinstance(v, (str, Path)) else v for k, v in values.items()}

    def tr_list(self, key: str) -> list[str]:
        value = self.raw(key)
        return list(value) if isinstance(value, list) else []


LRM = "‎"  # left-to-right mark
RLM = "‏"  # right-to-left mark
_BIDI_MARKS = str.maketrans("", "", LRM + RLM)


def _first_strong(text: str) -> str | None:
    for ch in text:
        if "֐" <= ch <= "ࣿ" or "יִ" <= ch <= "﷿" or "ﹰ" <= ch <= "﻿":
            return "rtl"
        if ch.isalpha():
            return "ltr"
    return None


def bidi_value(value: Any) -> str:
    """Wrap left-to-right data (e.g. "11.xls") in LRMs so an RTL paragraph can't reorder it.

    Only applied in right-to-left mode; Arabic values and pure numbers are left alone.
    """
    text = str(value)
    if translator.is_rtl and _first_strong(text) == "ltr":
        return f"{LRM}{text}{LRM}"
    return text


def paragraph(text: str) -> str:
    """Give a label the interface's paragraph direction even if it starts with data.

    Without this, "مهارات حياتية · Section 1" in the English UI (or an English course name
    in the Arabic UI) would take the direction of its first letter and flip alignment.
    """
    return (RLM if translator.is_rtl else LRM) + text


def strip_bidi(text: str) -> str:
    return text.translate(_BIDI_MARKS)


translator = Translator()


def tr(key: str, **values: Any) -> str:
    return translator.tr(key, **values)


def trn(key: str, count: int, **values: Any) -> str:
    return translator.trn(key, count, **values)


def get_language() -> str:
    return translator.language


def set_language(language: str) -> None:
    translator.set_language(language)


def is_rtl() -> bool:
    return translator.is_rtl


def format_date(value: dt.date | dt.datetime, style: str = "date") -> str:
    """Localized date text. Styles: ``date``, ``weekday_date``, ``long``, ``short``,
    ``datetime``, ``long_datetime``. Digits are always Western (0-9)."""
    months = translator.tr_list("date.months")
    months_short = translator.tr_list("date.months_short")
    weekdays = translator.tr_list("date.weekdays")
    weekdays_short = translator.tr_list("date.weekdays_short")
    d = value.date() if isinstance(value, dt.datetime) else value
    values = {
        "day": d.day,
        "year": d.year,
        "month": months[d.month - 1],
        "mon": months_short[d.month - 1],
        "weekday": weekdays[d.weekday()],
        "wd": weekdays_short[d.weekday()],
        "time": f"{value:%H:%M}" if isinstance(value, dt.datetime) else "",
    }
    return tr(f"date.format.{style}", **values)


def format_percent(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}%"


def tr_list(key: str) -> list[str]:
    return translator.tr_list(key)
