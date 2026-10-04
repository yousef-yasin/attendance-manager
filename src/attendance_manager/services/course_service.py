from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from attendance_manager.domain.errors import ValidationError
from attendance_manager.domain.models import Course, CourseStatus, Student
from attendance_manager.i18n import tr
from attendance_manager.importing.detection import ColumnMapping
from attendance_manager.importing.importer import (
    LoadedFile,
    RosterPreview,
    RosterStudent,
    build_roster,
    parse_table,
)

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CourseDetails:
    name: str
    section: str = ""
    semester: str = ""
    year: str = ""
    notes: str = ""

    def cleaned(self) -> CourseDetails:
        return CourseDetails(
            name=" ".join(self.name.split()),
            section=self.section.strip(),
            semester=self.semester.strip(),
            year=self.year.strip(),
            notes=self.notes.strip(),
        )

    def validate(self) -> None:
        if not self.name:
            raise ValidationError(tr("errors.course.name_required"))
        if len(self.name) > 150:
            raise ValidationError(tr("errors.course.name_too_long"))
        for label, value in (
            (tr("course_dialog.section"), self.section),
            (tr("course_dialog.semester"), self.semester),
            (tr("course_dialog.year"), self.year),
        ):
            if len(value) > 50:
                raise ValidationError(tr("errors.course.field_too_long", field=label))


@dataclass
class RosterDiff:
    added: list[RosterStudent] = field(default_factory=list)
    updated: list[tuple[Student, RosterStudent]] = field(default_factory=list)
    unchanged: int = 0
    missing: list[Student] = field(default_factory=list)


class CourseService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ------------------------------------------------------------------ queries
    def list_courses(self, include_archived: bool = True) -> list[Course]:
        return self.ctx.course_repo.all(include_archived)

    def get(self, course_id: int) -> Course:
        return self.ctx.course_repo.get(course_id)

    def counts(self, course_id: int) -> tuple[int, int]:
        return self.ctx.course_repo.counts(course_id)

    def students(self, course_id: int, active_only: bool = False) -> list[Student]:
        return self.ctx.student_repo.for_course(course_id, active_only)

    def info_columns(self, course_id: int) -> list[str]:
        """Master-file columns (besides ID and name), in file order."""
        columns: list[str] = []
        for student in self.ctx.student_repo.for_course(course_id):
            for key in student.info:
                if key not in columns:
                    columns.append(key)
        return columns

    def roster_imports(self, course_id: int) -> list:
        return self.ctx.roster_repo.for_course(course_id)

    # ---------------------------------------------------------------- previews
    @staticmethod
    def roster_preview(loaded: LoadedFile, mapping: ColumnMapping) -> RosterPreview:
        return build_roster(parse_table(loaded.workbook, mapping))

    def roster_diff(self, course_id: int, roster: RosterPreview) -> RosterDiff:
        existing = {s.student_key: s for s in self.ctx.student_repo.for_course(course_id)}
        diff = RosterDiff()
        seen: set[str] = set()
        for entry in roster.students:
            seen.add(entry.key)
            current = existing.get(entry.key)
            if current is None:
                diff.added.append(entry)
            elif (
                current.full_name != entry.full_name
                or current.student_number != entry.student_number
                or current.info != entry.info
                or not current.is_active
            ):
                diff.updated.append((current, entry))
            else:
                diff.unchanged += 1
        diff.missing = [s for k, s in existing.items() if k not in seen and s.is_active]
        return diff

    # ---------------------------------------------------------------- commands
    def create_course(
        self,
        details: CourseDetails,
        roster: RosterPreview,
        source_path: Path,
        *,
        allow_duplicate: bool = False,
    ) -> Course:
        details = details.cleaned()
        details.validate()
        repo = self.ctx.course_repo
        if not allow_duplicate and repo.find_duplicate(
            details.name, details.section, details.semester, details.year
        ):
            raise ValidationError(
                tr("errors.course.duplicate"),
                details="duplicate-course",
            )
        blob = self.ctx.files.store(source_path)
        with self.ctx.db.transaction():
            course_id = repo.add(
                details.name, details.section, details.semester, details.year, details.notes
            )
            file_id = self.ctx.file_repo.add(
                blob.sha256, source_path.name, blob.relative_path, blob.size_bytes
            )
            import_id = self.ctx.roster_repo.add(
                course_id,
                file_id,
                roster.table.mapping,
                len(roster.students),
                len(roster.students),
                0,
                0,
            )
            for position, entry in enumerate(roster.students, start=1):
                self.ctx.student_repo.add(
                    course_id,
                    entry.key,
                    entry.student_number,
                    entry.full_name,
                    entry.info,
                    position,
                    import_id,
                )
            self.ctx.audit.log(
                "course.create",
                "course",
                course_id,
                name=details.name,
                students=len(roster.students),
                file=source_path.name,
            )
        log.info("Created course %s with %d students", details.name, len(roster.students))
        return repo.get(course_id)

    def update_course(self, course_id: int, details: CourseDetails) -> Course:
        details = details.cleaned()
        details.validate()
        repo = self.ctx.course_repo
        if repo.find_duplicate(
            details.name, details.section, details.semester, details.year, exclude_id=course_id
        ):
            raise ValidationError(tr("errors.course.duplicate_other"))
        with self.ctx.db.transaction():
            repo.update(
                course_id,
                details.name,
                details.section,
                details.semester,
                details.year,
                details.notes,
            )
            self.ctx.audit.log("course.update", "course", course_id, name=details.name)
        return repo.get(course_id)

    def update_roster(
        self, course_id: int, roster: RosterPreview, source_path: Path, *, deactivate_missing: bool
    ) -> RosterDiff:
        """Apply a new master list. Never deletes students or their history."""
        diff = self.roster_diff(course_id, roster)
        blob = self.ctx.files.store(source_path)
        students = self.ctx.student_repo
        with self.ctx.db.transaction():
            file_id = self.ctx.file_repo.add(
                blob.sha256, source_path.name, blob.relative_path, blob.size_bytes
            )
            import_id = self.ctx.roster_repo.add(
                course_id,
                file_id,
                roster.table.mapping,
                len(roster.students),
                len(diff.added),
                len(diff.updated),
                len(diff.missing) if deactivate_missing else 0,
            )
            existing = {s.student_key: s for s in students.for_course(course_id)}
            for position, entry in enumerate(roster.students, start=1):
                current = existing.get(entry.key)
                if current is None:
                    students.add(
                        course_id,
                        entry.key,
                        entry.student_number,
                        entry.full_name,
                        entry.info,
                        position,
                        import_id,
                    )
                else:
                    students.update_from_roster(
                        current.id,
                        entry.student_number,
                        entry.full_name,
                        entry.info,
                        position,
                        import_id,
                    )
            if deactivate_missing:
                for student in diff.missing:
                    students.set_active(student.id, False)
            self.ctx.audit.log(
                "course.roster_update",
                "course",
                course_id,
                file=source_path.name,
                added=len(diff.added),
                updated=len(diff.updated),
                deactivated=len(diff.missing) if deactivate_missing else 0,
            )
        return diff

    def set_archived(self, course_id: int, archived: bool) -> None:
        with self.ctx.db.transaction():
            self.ctx.course_repo.set_status(
                course_id, CourseStatus.ARCHIVED if archived else CourseStatus.ACTIVE
            )
            self.ctx.audit.log(
                "course.archive" if archived else "course.unarchive", "course", course_id
            )

    def delete_course(self, course_id: int) -> Path:
        """Permanently delete a course. A full backup is taken first and returned."""
        course = self.ctx.course_repo.get(course_id)
        backup = self.ctx.backups.create_backup(
            reason=f"before deleting course {course.display_name}"
        )
        with self.ctx.db.transaction():
            self.ctx.course_repo.delete(course_id)
            self.ctx.audit.log(
                "course.delete", "course", course_id, name=course.display_name, backup=str(backup)
            )
        log.warning("Deleted course %s (backup %s)", course.display_name, backup)
        return backup
