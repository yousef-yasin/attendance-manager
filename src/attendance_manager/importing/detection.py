"""Automatic detection of where the student table is inside a sheet.

Real exports are rarely a clean header + rows. A Microsoft Teams attendance
report, for example, starts with a "1. Summary" block, then "2. Participants",
and the header row can even be missing (it is absent in one of the supplied
weekly files). Detection therefore works primarily from cell *content*:

1. For every column, count the cells that look like a student ID (see
   :func:`looks_like_student_id`, which also recognizes IDs inside e-mails/UPNs).
2. The column with the most hits is the ID column; header keywords break ties.
3. The first dense run of ID cells marks the start of the data; the non-blank
   row right above it is taken as the header row when it looks like one.
4. The name column is found by header keyword, otherwise by content.

The result carries a confidence level. The UI asks the instructor to confirm
the columns whenever confidence is not HIGH.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from attendance_manager.domain.ids import (
    clean_cell_text,
    looks_like_student_id,
    normalize_student_id,
)
from attendance_manager.i18n import tr
from attendance_manager.importing.reader import SheetData, WorkbookData


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ColumnMapping:
    sheet_index: int
    header_row: int | None
    first_data_row: int
    id_column: int
    name_column: int | None


@dataclass
class DetectionResult:
    mapping: ColumnMapping | None
    confidence: Confidence
    notes: list[str] = field(default_factory=list)


def _norm_header(text: str) -> str:
    text = clean_cell_text(text).casefold()
    text = re.sub(r"[_\-/.:()\[\]]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_ID_HEADERS_STRONG = (
    "student id",
    "studentid",
    "student no",
    "student number",
    "student num",
    "university id",
    "university number",
    "university no",
    "id number",
    "id no",
    "registration number",
    "registration no",
    "reg no",
    "reg number",
    "matric",
    "matriculation number",
    "academic number",
    "academic id",
    "الرقم الجامعي",
    "الرقم الجامعى",
    "رقم الطالب",
    "الرقم الأكاديمي",
)
_ID_HEADERS_WEAK = (
    "participant id",
    "upn",
    "user principal name",
    "email",
    "e mail",
    "mail",
    "email address",
    "username",
    "user name",
    "login",
    "البريد الالكتروني",
    "البريد",
)
_ID_HEADERS_EXACT = ("id", "no", "رقم")
_NAME_HEADERS_STRONG = (
    "student name",
    "full name",
    "name",
    "student full name",
    "display name",
    "الاسم",
    "اسم الطالب",
    "الاسم الكامل",
    "اسم",
)
_NAME_HEADERS_WEAK = ("participant", "attendee", "student", "full name english")
SERIAL_HEADERS = ("#", "no", "no.", "s/n", "sn", "serial", "seq", "م", "ت", "الرقم المتسلسل", "row")

_SECTION_TITLE_RE = re.compile(r"^\s*\d+\s*[.)]\s+\S")


def id_header_weight(text: str) -> int:
    h = _norm_header(text)
    if not h:
        return 0
    if any(h == k or h.startswith(k + " ") or h.endswith(" " + k) for k in _ID_HEADERS_STRONG):
        return 3
    if any(k in h for k in _ID_HEADERS_STRONG):
        return 3
    if any(h == k or k in h for k in _ID_HEADERS_WEAK):
        return 1
    if h in _ID_HEADERS_EXACT:
        return 2
    return 0


def name_header_weight(text: str) -> int:
    h = _norm_header(text)
    if not h:
        return 0
    if h in _NAME_HEADERS_STRONG or any(k in h for k in ("student name", "full name", "اسم")):
        return 3
    if "name" in h.split():
        return 2
    if any(k in h for k in _NAME_HEADERS_WEAK):
        return 1
    return 0


def is_header_like(text: str) -> bool:
    return id_header_weight(text) > 0 or name_header_weight(text) > 0


def is_serial_header(text: str) -> bool:
    return clean_cell_text(text).casefold() in SERIAL_HEADERS


def is_section_title(row: Sequence[Any]) -> bool:
    cells = [clean_cell_text(v) for v in row if clean_cell_text(v)]
    return len(cells) == 1 and bool(_SECTION_TITLE_RE.match(cells[0]))


def non_empty_count(row: Sequence[Any]) -> int:
    return sum(1 for v in row if clean_cell_text(v))


def _looks_like_name(value: Any) -> bool:
    text = clean_cell_text(value)
    if not text or "@" in text or any(ch.isdigit() for ch in text):
        return False
    words = [w for w in re.split(r"\s+", text) if w]
    letters = sum(ch.isalpha() for ch in text)
    return len(words) >= 2 and letters >= len(text.replace(" ", "")) * 0.8


def detect_layout(workbook: WorkbookData) -> DetectionResult:
    best: DetectionResult | None = None
    best_score = -1
    for index, sheet in enumerate(workbook.sheets):
        result, score = _detect_sheet(sheet, index)
        if score > best_score:
            best, best_score = result, score
    if best is None or best.mapping is None:
        return DetectionResult(
            mapping=None,
            confidence=Confidence.LOW,
            notes=[tr("import.notes.no_id_column")],
        )
    if len(workbook.sheets) > 1:
        best.notes.append(
            tr(
                "import.notes.multiple_sheets",
                count=len(workbook.sheets),
                sheet=workbook.sheets[best.mapping.sheet_index].name,
            )
        )
    return best


def _first_dense_run(hit_rows: list[int]) -> int:
    need = min(3, len(hit_rows))
    for i, row in enumerate(hit_rows):
        window = [r for r in hit_rows[i:] if r <= row + 5]
        if len(window) >= need:
            return row
    return hit_rows[0]


def _detect_sheet(sheet: SheetData, sheet_index: int) -> tuple[DetectionResult, int]:
    n_cols = sheet.n_cols
    hits: dict[int, list[int]] = {
        c: [r for r in range(sheet.n_rows) if looks_like_student_id(sheet.cell(r, c))]
        for c in range(n_cols)
    }
    max_hits = max((len(v) for v in hits.values()), default=0)
    if max_hits == 0:
        return DetectionResult(mapping=None, confidence=Confidence.LOW), 0

    # Provisional start of data, based on the column with the most hits.
    top_col = max(hits, key=lambda c: (len(hits[c]), -c))
    first_data_row = _extend_upwards(sheet, top_col, _first_dense_run(hits[top_col]))
    header_row = _find_header_row(sheet, first_data_row)
    header = (
        [clean_cell_text(sheet.cell(header_row, c)) for c in range(n_cols)]
        if header_row is not None
        else [""] * n_cols
    )

    contenders = [c for c in hits if len(hits[c]) >= max(1, 0.6 * max_hits)]
    contenders.sort(key=lambda c: (-id_header_weight(header[c]), -len(hits[c]), c))
    id_column = contenders[0]

    notes: list[str] = []
    confidence = Confidence.HIGH
    # Other columns with similar hit counts but different values are genuinely ambiguous
    # (e.g. a phone-number column next to the ID column without headers).
    for other in contenders[1:]:
        if id_header_weight(header[other]) == id_header_weight(
            header[id_column]
        ) and not _same_keys(sheet, id_column, other, first_data_row):
            confidence = Confidence.MEDIUM
            notes.append(tr("import.notes.ambiguous"))
            break

    data_rows = [
        r
        for r in range(first_data_row, sheet.n_rows)
        if non_empty_count(sheet.rows[r]) >= 2
        and not is_header_like(clean_cell_text(sheet.cell(r, id_column)))
    ]
    id_hits = sum(1 for r in data_rows if looks_like_student_id(sheet.cell(r, id_column)))
    ratio = id_hits / len(data_rows) if data_rows else 0.0
    if ratio < 0.5 or id_hits < 2:
        confidence = Confidence.LOW
        notes.append(tr("import.notes.few_ids"))
    elif ratio < 0.8 and confidence is Confidence.HIGH:
        confidence = Confidence.MEDIUM
        notes.append(tr("import.notes.some_ids"))

    name_column = _find_name_column(sheet, header, id_column, first_data_row)
    if header_row is None:
        notes.append(tr("import.notes.no_header"))

    mapping = ColumnMapping(
        sheet_index=sheet_index,
        header_row=header_row,
        first_data_row=first_data_row,
        id_column=id_column,
        name_column=name_column,
    )
    return DetectionResult(mapping=mapping, confidence=confidence, notes=notes), id_hits


def _same_keys(sheet: SheetData, a: int, b: int, start: int) -> bool:
    total = same = 0
    for r in range(start, sheet.n_rows):
        if is_header_like(clean_cell_text(sheet.cell(r, a))) or is_header_like(
            clean_cell_text(sheet.cell(r, b))
        ):
            continue  # a header row that was sorted into the data
        ka, kb = normalize_student_id(sheet.cell(r, a)), normalize_student_id(sheet.cell(r, b))
        if ka is None and kb is None:
            continue
        total += 1
        same += ka == kb
    return total > 0 and same / total >= 0.95


def _extend_upwards(sheet: SheetData, id_column: int, first_hit: int) -> int:
    """Include data rows directly above the first ID-like row.

    In a Teams report the organizer row (e-mail ``j.doe@...``) sits between
    the header and the first student row; it is data, not a header.
    """
    fill = non_empty_count(sheet.rows[first_hit])
    row = first_hit
    while row - 1 >= 0:
        candidate = sheet.rows[row - 1]
        id_text = clean_cell_text(sheet.cell(row - 1, id_column))
        if (
            not id_text
            or is_header_like(id_text)
            or is_section_title(candidate)
            or non_empty_count(candidate) < max(2, 0.6 * fill)
        ):
            break
        row -= 1
    return row


def _find_header_row(sheet: SheetData, first_data_row: int) -> int | None:
    r = first_data_row - 1
    while r >= 0 and non_empty_count(sheet.rows[r]) == 0:
        r -= 1
    if r < 0:
        return None
    row = sheet.rows[r]
    cells = [clean_cell_text(v) for v in row]
    filled = [c for c in cells if c]
    data_filled = non_empty_count(sheet.rows[first_data_row])
    if len(filled) < 2 or len(filled) < 0.5 * data_filled:
        return None
    if any(looks_like_student_id(v) for v in row):
        return None
    textual = sum(1 for c in filled if not re.fullmatch(r"[\d.,\s:/-]+", c))
    if any(is_header_like(c) for c in filled) or textual == len(filled):
        return r
    return None


def _find_name_column(
    sheet: SheetData, header: list[str], id_column: int, start: int
) -> int | None:
    weighted = [(name_header_weight(h), c) for c, h in enumerate(header) if c != id_column]
    weighted = [w for w in weighted if w[0] > 0]
    if weighted:
        weighted.sort(key=lambda w: (-w[0], w[1]))
        return weighted[0][1]
    best_col, best_ratio = None, 0.0
    rows = [r for r in range(start, sheet.n_rows) if clean_cell_text(sheet.cell(r, id_column))]
    if not rows:
        return None
    for c in range(sheet.n_cols):
        if c == id_column:
            continue
        ratio = sum(1 for r in rows if _looks_like_name(sheet.cell(r, c))) / len(rows)
        if ratio > best_ratio + 1e-9:
            best_col, best_ratio = c, ratio
    return best_col if best_ratio >= 0.6 else None


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
