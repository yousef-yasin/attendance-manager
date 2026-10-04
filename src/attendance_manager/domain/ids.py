"""Student ID normalization.

Matching never uses row order: every row is reduced to a *match key* and students
are compared by key. The key tolerates the differences seen in real exports:

* surrounding / internal whitespace, non-breaking and zero-width spaces
* numeric cells (``202400123.0``) versus text cells (``"202400123"``)
* Excel's text marker (``'202400123``)
* e-mail / UPN style identifiers (``202400123@university.edu`` -> ``202400123``)
* letter case (``s123456`` == ``S123456``)
* leading zeros on purely numeric IDs (``0012345`` == ``12345``), because Excel
  silently drops them when a column is stored as numbers.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_WHITESPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"^([^@\s]+)@[^@\s]+$")
_FLOAT_TEXT_RE = re.compile(r"^[+-]?\d+(\.0+)?$")
_SCIENTIFIC_RE = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+]?\d+$")
_DIGITS_RE = re.compile(r"\d")
_ID_CHARS_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")
_DURATION_RE = re.compile(r"^(\d+h)?(\d+m)?(\d+s)?$", re.IGNORECASE)

MIN_ID_DIGITS = 4
MAX_ID_LENGTH = 32


def clean_cell_text(value: Any) -> str:
    """Convert any spreadsheet cell value to trimmed display text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, dt.date):
        return value.isoformat()
    text = unicodedata.normalize("NFKC", str(value)).translate(_INVISIBLE)
    text = text.replace(" ", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _strip_id_decorations(value: Any) -> str:
    text = clean_cell_text(value)
    if not text:
        return ""
    text = text.lstrip("'").strip()
    email = _EMAIL_RE.match(text)
    if email:
        text = email.group(1)
    text = _WHITESPACE_RE.sub("", text)
    if _FLOAT_TEXT_RE.match(text):
        text = text.split(".")[0].lstrip("+")
    elif _SCIENTIFIC_RE.match(text):
        try:
            number = float(text)
            if number.is_integer():
                text = str(int(number))
        except ValueError:
            pass
    return text


def display_student_id(value: Any) -> str:
    """The ID as it should be shown to the instructor (case and zeros preserved)."""
    return _strip_id_decorations(value)


def normalize_student_id(value: Any) -> str | None:
    """Return the canonical match key for an ID cell, or ``None`` when empty."""
    text = _strip_id_decorations(value)
    if not text:
        return None
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text.casefold()


def looks_like_student_id(value: Any) -> bool:
    """Heuristic used for column detection: does this cell hold a student ID?

    Accepts pure numbers with at least four digits and short alphanumeric codes
    containing at least four digits (``S1234567``, ``2021-cs-001``), including
    when wrapped in an e-mail / UPN. Dates, names and sentences are rejected.
    """
    if isinstance(value, (dt.date, dt.datetime, bool)):
        return False
    raw = clean_cell_text(value)
    # Durations ("1h 3m 50s") and other spaced tokens are not IDs; spaced digit
    # groups ("2024 00123") still are.
    if re.search(r"[A-Za-z]\s+\w|\w\s+[A-Za-z]", raw):
        return False
    if _DURATION_RE.match(raw.replace(" ", "")):
        return False
    text = _strip_id_decorations(value)
    if not text or len(text) > MAX_ID_LENGTH:
        return False
    if not _ID_CHARS_RE.match(text):
        return False
    digits = len(_DIGITS_RE.findall(text))
    if digits < MIN_ID_DIGITS:
        return False
    # Reject date-like strings such as 08-07-2026 or 2026/07/08.
    if re.fullmatch(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", text):
        return False
    # Mostly digits: letters may only be a short prefix/suffix.
    return digits >= len(text) * 0.5
