"""Domain entities shared by persistence, services and UI."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"


class CourseStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    #: Removed by the instructor. Kept in the database (and recoverable) but
    #: excluded from statistics.
    REMOVED = "removed"


class StudentStanding(str, Enum):
    PERFECT = "Perfect"
    GOOD = "Good"
    WARNING = "Warning"
    AT_RISK = "At risk"
    NO_SESSIONS = "No sessions"


@dataclass(frozen=True)
class Course:
    id: int
    uuid: str
    name: str
    section: str
    semester: str
    year: str
    notes: str
    status: CourseStatus
    created_at: dt.datetime
    updated_at: dt.datetime

    @property
    def term_description(self) -> str:
        """Localized "Section 1 · Summer 2026" (the values themselves are data)."""
        from attendance_manager.i18n import tr

        parts = []
        if self.section:
            parts.append(tr("course.section", section=self.section))
        term = " ".join(p for p in (self.semester, self.year) if p)
        if term:
            parts.append(term)
        return " · ".join(parts)

    @property
    def display_name(self) -> str:
        term = self.term_description
        return f"{self.name} · {term}" if term else self.name


@dataclass(frozen=True)
class Student:
    id: int
    course_id: int
    student_key: str
    student_number: str
    full_name: str
    #: Every column of the master file (header -> text), in file order.
    info: dict[str, str]
    roster_position: int
    is_active: bool


@dataclass(frozen=True)
class StoredFile:
    id: int
    sha256: str
    original_filename: str
    relative_path: str
    size_bytes: int
    stored_at: dt.datetime


@dataclass(frozen=True)
class AttendanceSession:
    id: int
    uuid: str
    course_id: int
    session_number: int
    title: str
    session_date: dt.date
    original_filename: str
    file_id: int
    file_sha256: str
    uploaded_at: dt.datetime
    present_count: int
    absent_count: int
    unmatched_count: int
    status: SessionStatus
    removed_at: dt.datetime | None
    removed_reason: str
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.present_count + self.absent_count

    @property
    def percentage(self) -> float | None:
        return (self.present_count / self.total * 100.0) if self.total else None

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        from attendance_manager.i18n import tr

        return tr("sessions.default_title", number=self.session_number)


@dataclass(frozen=True)
class AttendanceRecord:
    session_id: int
    student_id: int
    status: AttendanceStatus
    source_row: int | None
    raw_identifier: str


@dataclass(frozen=True)
class SessionParticipant:
    """A row of an uploaded attendance file (the processed result)."""

    session_id: int
    row_number: int
    raw_identifier: str
    student_key: str | None
    name: str
    matched_student_id: int | None
    data: dict[str, str]


@dataclass(frozen=True)
class RosterImport:
    id: int
    course_id: int
    file_id: int
    original_filename: str
    imported_at: dt.datetime
    student_count: int
    added_count: int
    updated_count: int
    deactivated_count: int
