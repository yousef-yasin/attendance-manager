"""Adding and browsing attendance sessions.

Workflow: ``load_file`` (can run in a worker thread) -> ``build_preview`` ->
instructor reviews -> ``save_session``. Saving stores the original file, the
parsed rows (processed result) and one immutable record per active student.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from attendance_manager.domain.errors import AttendanceError, ValidationError
from attendance_manager.domain.matching import MatchResult, match_attendance
from attendance_manager.domain.models import (
    AttendanceSession,
    AttendanceStatus,
    SessionParticipant,
    SessionStatus,
    Student,
)
from attendance_manager.i18n import format_date, tr, trn
from attendance_manager.importing.detection import ColumnMapping
from attendance_manager.importing.importer import (
    LoadedFile,
    ParsedTable,
    detect_session_date,
    parse_table,
    participant_rows,
)
from attendance_manager.persistence.file_store import sha256_of

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext

log = logging.getLogger(__name__)


class Severity(str, Enum):
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class PreviewNotice:
    severity: Severity
    message: str


class DuplicateSessionError(AttendanceError):
    """The exact same file was already uploaded to this course."""

    def __init__(self, existing: AttendanceSession) -> None:
        super().__init__(
            tr(
                "errors.duplicate_session",
                session=existing.label,
                date=format_date(existing.session_date),
            )
        )
        self.existing = existing


@dataclass
class SessionPreview:
    course_id: int
    source_path: Path
    sha256: str
    table: ParsedTable
    match: MatchResult
    students_by_key: dict[str, Student]
    detected_date: dt.date | None
    suggested_number: int
    notices: list[PreviewNotice] = field(default_factory=list)
    duplicate_of: AttendanceSession | None = None

    @property
    def mapping(self) -> ColumnMapping:
        return self.table.mapping

    @property
    def present_students(self) -> list[Student]:
        return [self.students_by_key[k] for k in self.match.present_keys]

    @property
    def absent_students(self) -> list[Student]:
        return [self.students_by_key[k] for k in self.match.absent_keys]

    @property
    def suggested_title(self) -> str:
        return tr("sessions.default_title", number=self.suggested_number)


@dataclass
class SessionDetail:
    session: AttendanceSession
    present: list[Student]
    absent: list[Student]
    unmatched: list[SessionParticipant]
    participants: list[SessionParticipant]


class AttendanceService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ------------------------------------------------------------------ preview
    def build_preview(
        self, course_id: int, loaded: LoadedFile, mapping: ColumnMapping
    ) -> SessionPreview:
        course = self.ctx.course_repo.get(course_id)
        table = parse_table(loaded.workbook, mapping)
        students = self.ctx.student_repo.for_course(course_id, active_only=True)
        if not students:
            raise ValidationError(tr("errors.course_has_no_students", course=course.name))
        by_key = {s.student_key: s for s in students}
        match = match_attendance(by_key.keys(), participant_rows(table))
        sha = sha256_of(loaded.workbook.path)
        preview = SessionPreview(
            course_id=course_id,
            source_path=loaded.workbook.path,
            sha256=sha,
            table=table,
            match=match,
            students_by_key=by_key,
            detected_date=detect_session_date(table),
            suggested_number=self.ctx.session_repo.next_number(course_id),
        )
        self._add_notices(preview)
        return preview

    def _add_notices(self, p: SessionPreview) -> None:
        sessions = self.ctx.session_repo.for_course(p.course_id)
        notices = p.notices
        exact = next((s for s in sessions if s.file_sha256 == p.sha256), None)
        if exact is not None:
            p.duplicate_of = exact
            state = tr("notices.currently_removed") if exact.status is SessionStatus.REMOVED else ""
            notices.append(
                PreviewNotice(
                    Severity.DANGER,
                    tr(
                        "notices.exact_duplicate",
                        session=exact.label,
                        state=state,
                        date=format_date(exact.uploaded_at.astimezone()),
                    ),
                )
            )
        if p.sha256 in self.ctx.roster_repo.file_hashes(p.course_id):
            notices.append(
                PreviewNotice(
                    Severity.DANGER,
                    tr("notices.is_master_list"),
                )
            )
        if p.match.present_count == 0:
            notices.append(
                PreviewNotice(
                    Severity.DANGER,
                    tr("notices.nobody_matched"),
                )
            )
        elif p.match.recognized_ratio < 0.5:
            notices.append(
                PreviewNotice(
                    Severity.WARNING,
                    tr("notices.mostly_unknown"),
                )
            )
        if exact is None:
            present_ids = frozenset(s.id for s in p.present_students)
            for session_id, ids in self.ctx.session_repo.present_sets(p.course_id).items():
                if ids == present_ids and present_ids:
                    same = next(s for s in sessions if s.id == session_id)
                    notices.append(
                        PreviewNotice(
                            Severity.WARNING,
                            tr("notices.same_students", session=same.label),
                        )
                    )
                    break
            same_name = [
                s
                for s in sessions
                if s.original_filename.casefold() == p.source_path.name.casefold()
            ]
            if same_name:
                notices.append(
                    PreviewNotice(
                        Severity.INFO,
                        tr("notices.same_name", session=same_name[0].label),
                    )
                )
        if p.detected_date is not None:
            same_day = [
                s
                for s in sessions
                if s.session_date == p.detected_date and s.status is SessionStatus.ACTIVE
            ]
            if same_day:
                notices.append(
                    PreviewNotice(Severity.INFO, tr("notices.same_date", session=same_day[0].label))
                )
        if p.match.unmatched:
            notices.append(
                PreviewNotice(
                    Severity.INFO,
                    trn("notices.unmatched", len(p.match.unmatched)),
                )
            )
        repeated = {r.key for r in p.match.repeated if r.key}
        if repeated:
            notices.append(
                PreviewNotice(
                    Severity.INFO,
                    trn("notices.repeated", len(repeated)),
                )
            )

    # --------------------------------------------------------------------- save
    def save_session(
        self,
        preview: SessionPreview,
        *,
        title: str,
        session_date: dt.date,
        allow_duplicate: bool = False,
    ) -> AttendanceSession:
        title = " ".join(title.split())
        if len(title) > 120:
            raise ValidationError(tr("errors.session_title_too_long"))
        if preview.duplicate_of is not None and not allow_duplicate:
            raise DuplicateSessionError(preview.duplicate_of)
        # Re-check the roster: it may have changed since the preview was built.
        current = {
            s.student_key
            for s in self.ctx.student_repo.for_course(preview.course_id, active_only=True)
        }
        if current != set(preview.students_by_key):
            raise ValidationError(tr("errors.roster_changed"))

        blob = self.ctx.files.store(preview.source_path)
        if blob.sha256 != preview.sha256:
            raise ValidationError(tr("errors.file_changed"))
        repo = self.ctx.session_repo
        match = preview.match
        with self.ctx.db.transaction():
            number = repo.next_number(preview.course_id)
            file_id = self.ctx.file_repo.add(
                blob.sha256, preview.source_path.name, blob.relative_path, blob.size_bytes
            )
            session_id = repo.add(
                preview.course_id,
                number,
                title or tr("sessions.default_title", number=number),
                session_date,
                file_id,
                preview.mapping,
                {**preview.table.metadata, "Sheet": preview.table.sheet_name},
                match.present_count,
                match.absent_count,
                len(match.unmatched),
            )
            records = []
            for key, status in match.statuses.items():
                student = preview.students_by_key[key]
                evidence = match.evidence.get(key)
                records.append(
                    (
                        student.id,
                        status,
                        evidence.row_number if evidence else None,
                        evidence.raw_identifier if evidence else "",
                    )
                )
            repo.add_records(session_id, records)
            repo.add_participants(
                session_id,
                [
                    (
                        row.row_number,
                        row.raw_identifier,
                        row.key,
                        row.name,
                        preview.students_by_key[row.key].id
                        if row.key in preview.students_by_key
                        else None,
                        row.values,
                    )
                    for row in preview.table.rows
                ],
            )
            self.ctx.audit.log(
                "session.create",
                "session",
                session_id,
                course_id=preview.course_id,
                file=preview.source_path.name,
                present=match.present_count,
                absent=match.absent_count,
                duplicate_override=allow_duplicate,
            )
        log.info(
            "Saved session %s for course %s: %d present / %d absent",
            number,
            preview.course_id,
            match.present_count,
            match.absent_count,
        )
        return repo.get(session_id)

    # ----------------------------------------------------------------- browsing
    def sessions(self, course_id: int, include_removed: bool = True) -> list[AttendanceSession]:
        return self.ctx.session_repo.for_course(course_id, include_removed)

    def session_detail(self, session_id: int) -> SessionDetail:
        session = self.ctx.session_repo.get(session_id)
        students = {s.id: s for s in self.ctx.student_repo.for_course(session.course_id)}
        present: list[Student] = []
        absent: list[Student] = []
        for record in self.ctx.session_repo.records(session_id):
            student = students.get(record.student_id)
            if student is None:
                continue
            (present if record.status is AttendanceStatus.PRESENT else absent).append(student)
        participants = self.ctx.session_repo.participants(session_id)
        key = lambda s: (s.roster_position, s.id)  # noqa: E731
        return SessionDetail(
            session=session,
            present=sorted(present, key=key),
            absent=sorted(absent, key=key),
            unmatched=[p for p in participants if p.matched_student_id is None],
            participants=participants,
        )

    def original_file_copy(self, session_id: int, destination_dir: Path | None = None) -> Path:
        """Write a copy of the original upload (the stored original stays untouched)."""
        session = self.ctx.session_repo.get(session_id)
        stored = self.ctx.file_repo.get(session.file_id)
        target_dir = destination_dir or (self.ctx.paths.temp_dir / f"session-{session.id}")
        return self.ctx.files.export_copy(
            stored.relative_path, target_dir / stored.original_filename
        )

    def verify_original(self, session_id: int) -> bool:
        session = self.ctx.session_repo.get(session_id)
        stored = self.ctx.file_repo.get(session.file_id)
        return self.ctx.files.verify(stored.relative_path, stored.sha256)

    # ----------------------------------------------------------------- commands
    def remove_session(self, session_id: int, reason: str = "") -> None:
        """Exclude a session from statistics. Nothing is deleted; it can be restored."""
        with self.ctx.db.transaction():
            self.ctx.session_repo.set_removed(session_id, True, reason.strip())
            self.ctx.audit.log("session.remove", "session", session_id, reason=reason)

    def restore_session(self, session_id: int) -> None:
        with self.ctx.db.transaction():
            self.ctx.session_repo.set_removed(session_id, False)
            self.ctx.audit.log("session.restore", "session", session_id)

    def update_session_details(self, session_id: int, title: str, session_date: dt.date) -> None:
        title = " ".join(title.split())
        if not title:
            raise ValidationError(tr("errors.session_title_required"))
        with self.ctx.db.transaction():
            self.ctx.session_repo.update_details(session_id, title, session_date)
            self.ctx.audit.log(
                "session.rename", "session", session_id, title=title, date=session_date.isoformat()
            )
