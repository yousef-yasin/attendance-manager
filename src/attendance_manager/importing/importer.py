"""Turn a spreadsheet + column mapping into structured rows.

Two consumers:

* :func:`build_roster` — master student list (``00.xls``) -> students;
* :func:`parse_attendance` — weekly file -> participant rows for matching.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from attendance_manager.domain.errors import ImportFileError
from attendance_manager.domain.ids import (
    clean_cell_text,
    display_student_id,
    looks_like_student_id,
    normalize_student_id,
)
from attendance_manager.domain.matching import ParticipantRow
from attendance_manager.i18n import tr
from attendance_manager.importing.detection import (
    ColumnMapping,
    Confidence,
    DetectionResult,
    column_letter,
    detect_layout,
    is_header_like,
    is_section_title,
    is_serial_header,
    non_empty_count,
)
from attendance_manager.importing.reader import WorkbookData, read_workbook


@dataclass(frozen=True)
class ParsedRow:
    row_number: int  # 1-based, as shown in Excel
    raw_identifier: str
    key: str | None
    display_id: str
    name: str
    id_like: bool
    values: dict[str, str]


@dataclass(frozen=True)
class SkippedRow:
    row_number: int
    reason: str


@dataclass
class ParsedTable:
    file_name: str
    sheet_name: str
    file_format: str
    mapping: ColumnMapping
    column_names: list[str]
    rows: list[ParsedRow]
    skipped: list[SkippedRow]
    metadata: dict[str, str]
    serial_columns: set[int] = field(default_factory=set)

    @property
    def id_column_name(self) -> str:
        return self.column_names[self.mapping.id_column]

    @property
    def name_column_name(self) -> str | None:
        c = self.mapping.name_column
        return self.column_names[c] if c is not None else None


@dataclass
class LoadedFile:
    """A read workbook plus the automatically detected layout."""

    workbook: WorkbookData
    detection: DetectionResult

    @property
    def needs_confirmation(self) -> bool:
        return self.detection.confidence is not Confidence.HIGH or self.detection.mapping is None


def load_file(path: Path | str) -> LoadedFile:
    workbook = read_workbook(path)
    return LoadedFile(workbook=workbook, detection=detect_layout(workbook))


def column_names_for(workbook: WorkbookData, mapping: ColumnMapping) -> list[str]:
    sheet = workbook.sheets[mapping.sheet_index]
    header_row = mapping.header_row
    if header_row is None:
        # A header can end up inside the data when the sheet was sorted with it.
        header_row = next(
            (
                r
                for r in range(mapping.first_data_row, sheet.n_rows)
                if is_header_like(clean_cell_text(sheet.cell(r, mapping.id_column)))
                and not looks_like_student_id(sheet.cell(r, mapping.id_column))
                and non_empty_count(sheet.rows[r]) >= 2
            ),
            None,
        )
    names: list[str] = []
    seen: dict[str, int] = {}
    for c in range(sheet.n_cols):
        name = clean_cell_text(sheet.cell(header_row, c)) if header_row is not None else ""
        if not name:
            if c == mapping.id_column:
                name = tr("import.generic.student_id")
            elif c == mapping.name_column:
                name = tr("import.generic.name")
            else:
                name = tr("import.generic.column", letter=column_letter(c))
        count = seen.get(name.casefold(), 0)
        seen[name.casefold()] = count + 1
        names.append(name if count == 0 else f"{name} ({count + 1})")
    return names


def parse_table(workbook: WorkbookData, mapping: ColumnMapping) -> ParsedTable:
    if not 0 <= mapping.sheet_index < len(workbook.sheets):
        raise ImportFileError(tr("errors.import.no_sheet"))
    sheet = workbook.sheets[mapping.sheet_index]
    if not 0 <= mapping.id_column < sheet.n_cols:
        raise ImportFileError(tr("errors.import.no_column"))
    names = column_names_for(workbook, mapping)
    serial = {
        c
        for c in range(sheet.n_cols)
        if mapping.header_row is not None
        and c not in (mapping.id_column, mapping.name_column)
        and is_serial_header(clean_cell_text(sheet.cell(mapping.header_row, c)))
    }

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    start = mapping.first_data_row
    if mapping.header_row is not None:
        start = max(start, mapping.header_row + 1)
    for r in range(start, sheet.n_rows):
        raw_row = sheet.rows[r]
        if non_empty_count(raw_row) == 0:
            continue
        if is_section_title(raw_row) and rows:
            # e.g. "3. In-Meeting Activities" — a different table follows.
            break
        id_cell = sheet.cell(r, mapping.id_column)
        raw_id = clean_cell_text(id_cell)
        if raw_id and is_header_like(raw_id) and not looks_like_student_id(id_cell):
            skipped.append(SkippedRow(r + 1, tr("import.skipped.header")))
            continue
        values = {
            names[c]: clean_cell_text(sheet.cell(r, c))
            for c in range(sheet.n_cols)
            if c not in serial
        }
        name = (
            clean_cell_text(sheet.cell(r, mapping.name_column))
            if mapping.name_column is not None
            else ""
        )
        if not raw_id:
            if non_empty_count(raw_row) == 1 and not name:
                skipped.append(
                    SkippedRow(r + 1, tr("import.skipped.text", text=_first_text(raw_row)))
                )
                continue
            rows.append(ParsedRow(r + 1, "", None, "", name, False, values))
            continue
        if non_empty_count(raw_row) == 1 and not looks_like_student_id(id_cell):
            # A lone label such as "Total" under the table.
            skipped.append(SkippedRow(r + 1, tr("import.skipped.text", text=_first_text(raw_row))))
            continue
        rows.append(
            ParsedRow(
                row_number=r + 1,
                raw_identifier=raw_id,
                key=normalize_student_id(id_cell),
                display_id=display_student_id(id_cell),
                name=name,
                id_like=looks_like_student_id(id_cell),
                values=values,
            )
        )

    return ParsedTable(
        file_name=workbook.path.name,
        sheet_name=sheet.name,
        file_format=workbook.file_format,
        mapping=mapping,
        column_names=names,
        rows=rows,
        skipped=skipped,
        metadata=extract_metadata(workbook, mapping),
        serial_columns=serial,
    )


def _first_text(row: list[Any]) -> str:
    text = next((clean_cell_text(v) for v in row if clean_cell_text(v)), "")
    return text if len(text) <= 40 else text[:37] + "…"


def extract_metadata(workbook: WorkbookData, mapping: ColumnMapping) -> dict[str, str]:
    """Label/value pairs above the table (e.g. Teams "Meeting title", "Start time")."""
    sheet = workbook.sheets[mapping.sheet_index]
    end = mapping.header_row if mapping.header_row is not None else mapping.first_data_row
    meta: dict[str, str] = {}
    for r in range(0, end):
        cells = [(c, v) for c, v in enumerate(sheet.rows[r]) if clean_cell_text(v)]
        if len(cells) != 2:
            continue
        label = clean_cell_text(cells[0][1])
        value = cells[1][1]
        if not label or looks_like_student_id(label) or len(label) > 60:
            continue
        meta[label] = (
            value.isoformat(sep=" ") if isinstance(value, dt.datetime) else clean_cell_text(value)
        )
    return meta


# --------------------------------------------------------------------------- roster


@dataclass(frozen=True)
class RosterStudent:
    key: str
    student_number: str
    full_name: str
    info: dict[str, str]
    row_number: int


@dataclass
class RosterPreview:
    table: ParsedTable
    students: list[RosterStudent]
    duplicates: list[tuple[RosterStudent, ParsedRow]]
    warnings: list[str]

    @property
    def info_columns(self) -> list[str]:
        excluded = {self.table.id_column_name, self.table.name_column_name}
        return [
            n
            for i, n in enumerate(self.table.column_names)
            if n not in excluded and i not in self.table.serial_columns
        ]


def build_roster(table: ParsedTable) -> RosterPreview:
    students: dict[str, RosterStudent] = {}
    duplicates: list[tuple[RosterStudent, ParsedRow]] = []
    warnings: list[str] = []
    excluded = {table.id_column_name, table.name_column_name}

    for row in table.rows:
        if row.key is None:
            warnings.append(tr("import.warn.no_id", row=row.row_number))
            continue
        if not row.id_like:
            warnings.append(tr("import.warn.not_id", row=row.row_number, value=row.raw_identifier))
            continue
        if row.key in students:
            duplicates.append((students[row.key], row))
            warnings.append(
                tr(
                    "import.warn.duplicate",
                    row=row.row_number,
                    id=row.display_id,
                    first=students[row.key].row_number,
                )
            )
            continue
        info = {k: v for k, v in row.values.items() if k not in excluded}
        students[row.key] = RosterStudent(
            key=row.key,
            student_number=row.display_id,
            full_name=row.name or tr("import.no_name"),
            info=info,
            row_number=row.row_number,
        )
        if not row.name:
            warnings.append(tr("import.warn.no_name", row=row.row_number, id=row.display_id))

    if not students:
        raise ImportFileError(tr("errors.import.no_students"))
    if table.mapping.name_column is None:
        warnings.insert(0, tr("import.warn.no_name_column"))
    return RosterPreview(
        table=table, students=list(students.values()), duplicates=duplicates, warnings=warnings
    )


# --------------------------------------------------------------------------- attendance


def participant_rows(table: ParsedTable) -> list[ParticipantRow]:
    return [
        ParticipantRow(
            row_number=r.row_number,
            raw_identifier=r.raw_identifier,
            key=r.key,
            name=r.name,
            data=r.values,
        )
        for r in table.rows
    ]


_DATE_KEYS = (
    "start time",
    "meeting start time",
    "session date",
    "lecture date",
    "date",
    "start date",
    "meeting date",
    "class date",
    "التاريخ",
)
_JOIN_KEYS = ("first join", "join time", "joined", "first seen", "time joined")
_DATETIME_FORMATS = (
    "%m/%d/%y, %I:%M:%S %p",
    "%m/%d/%Y, %I:%M:%S %p",
    "%m/%d/%y, %I:%M %p",
    "%m/%d/%Y, %I:%M %p",
    "%m/%d/%y %I:%M:%S %p",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%m/%d/%y",
)


def parse_datetime_text(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    text = clean_cell_text(value)
    if not text:
        return None
    text = re.sub(r"\s*\((UTC|GMT)[^)]*\)\s*$", "", text)
    for fmt in _DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def detect_session_date(table: ParsedTable) -> dt.date | None:
    """Best guess of the lecture date: summary "Start time", else earliest join time."""
    for label, value in table.metadata.items():
        if label.casefold().strip(" :") in _DATE_KEYS:
            parsed = parse_datetime_text(value)
            if parsed:
                return parsed.date()
    join_cols = [n for n in table.column_names if n.casefold().strip() in _JOIN_KEYS]
    dates = [
        parsed.date()
        for col in join_cols
        for row in table.rows
        if (parsed := parse_datetime_text(row.values.get(col, "")))
    ]
    return min(dates) if dates else None


def file_based_mapping(loaded: LoadedFile) -> ColumnMapping:
    if loaded.detection.mapping is None:
        raise ImportFileError(tr("errors.import.detect_failed"))
    return loaded.detection.mapping


def load_roster(path: Path | str, mapping: ColumnMapping | None = None) -> RosterPreview:
    """Convenience: read, detect (unless a mapping is given) and build a roster."""
    loaded = load_file(path)
    return build_roster(parse_table(loaded.workbook, mapping or file_based_mapping(loaded)))
